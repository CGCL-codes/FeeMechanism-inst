// varying-elasticity runs the Appendix B.3 experiment in which the inbound
// elasticity epsilon_{j->0} is a function of Chain 0's own base fee rather
// than a constant. Three shapes are built in, each passing through 16 at the
// equilibrium price x = 1:
//
//	log       eps(x) = max(0, 16 + ln x)
//	linear    eps(x) = min(16x, 32)
//	logistic  eps(x) = 32 x^2 / (x^2 + 1)
//
// It reruns the Figure 4c sweep (delta x alpha_in, spike latency, d_max = 5)
// under the chosen shape, which is the data behind Figure 14.
package main

import (
	"encoding/csv"
	"flag"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"sync"

	"gas-for-multiple-shards/core"
)

const (
	targetLoad     = 0.5
	convergenceTol = targetLoad * 1e-3
	window         = 50
	totalSteps     = 50100
	gasLimit       = 2_000_000.0
	anchor         = 16.0
	// mempoolCap is each chain's transaction-pool bound, in multiples of the
	// block gas limit, matching the rest of the protocol.
	mempoolCap = 20.0
)

// shapeRamp returns the price-driven elasticity shape as a knot table. The
// dense shapes sample x = exp(-18 + 27 i/560) for i = 0..560, so the table
// covers e^-18 to e^9 and the leading (0, 0) knot closes the range below.
// Every knot and value is rounded to 10 significant decimal digits, which
// pins the shape definition exactly and keeps the table independent of the
// last-bit behaviour of any one exp/log implementation.
func shapeRamp(name string) (core.ElasticityRamp, error) {
	round10 := func(value float64) float64 {
		rounded, _ := strconv.ParseFloat(strconv.FormatFloat(value, 'g', 10, 64), 64)
		return rounded
	}
	knots, values := []float64{0}, []float64{0}
	dense := func(eval func(x float64) float64) {
		for index := 0; index <= 560; index++ {
			x := math.Exp(-18 + 27*float64(index)/560)
			knots = append(knots, round10(x))
			values = append(values, round10(eval(x)))
		}
	}
	switch name {
	case "log":
		dense(func(x float64) float64 { return math.Max(0, anchor+math.Log(x)) })
	case "linear":
		knots = []float64{0, 2, 10000}
		values = []float64{0, 2 * anchor, 2 * anchor}
	case "logistic":
		dense(func(x float64) float64 { return 2 * anchor * x * x / (x*x + 1) })
	default:
		return core.ElasticityRamp{}, fmt.Errorf("unknown shape %q", name)
	}
	return core.ElasticityRamp{
		Enabled: true, Chain: 0, Knots: knots, Values: values, Driver: "price",
	}, nil
}

func configFor(alpha, delta float64, maxDelay int, ramp core.ElasticityRamp) core.Config {
	target := gasLimit * targetLoad
	inbound := target * alpha
	diagonal := target - inbound
	cross := inbound / 4
	weights := make([]float64, maxDelay)
	weights[maxDelay-1] = 1
	return core.Config{
		Simulation: core.SimulationConfig{
			TotalSteps: totalSteps, LTarget: targetLoad, Delta: delta,
			MempoolCap: mempoolCap,
			DemandShock: core.DemandShockConfig{
				Enabled: true, StartStep: 100, EndStep: 101,
				Multiplier: 1.01, TargetShards: []int{0},
			},
		},
		Network: core.NetworkConfig{NumShards: 3},
		Shards: []core.ShardSpec{
			{ID: 0, GMax: gasLimit}, {ID: 1, GMax: gasLimit}, {ID: 2, GMax: gasLimit},
		},
		Demand: core.DemandConfig{
			BaseDemandMatrix: [][]float64{
				{diagonal, 0, 0},
				{inbound / 2, diagonal, cross},
				{inbound / 2, cross, diagonal},
			},
			LambdaMatrix: [][]float64{{1.5, 1.5, 1.5}, {1.5, 1.5, 1.5}, {1.5, 1.5, 1.5}},
			EpsilonMatrix: [][]float64{
				{0, 1.5, 1.5}, {anchor, 0, 1.5}, {anchor, 1.5, 0},
			},
			InboundElasticityRamp: ramp,
		},
		Delay: core.DelayConfig{MaxDelay: maxDelay, Weights: weights},
	}
}

func runGrid(ramp core.ElasticityRamp, workers int, output string) error {
	deltas := make([]float64, 0, 125)
	for index := 0; index < 125; index++ {
		deltas = append(deltas, float64(index+1)/1000)
	}
	alphas := make([]float64, 0, 99)
	for index := 1; index <= 99; index++ {
		alphas = append(alphas, float64(index)/100)
	}

	type cell struct {
		delta, alpha   float64
		summary        core.ObservedLoadSummary
		epsMin, epsMax float64
	}
	cells := make([]cell, len(deltas)*len(alphas))
	var group sync.WaitGroup
	slots := make(chan struct{}, workers)
	for deltaIndex, delta := range deltas {
		for alphaIndex, alpha := range alphas {
			index := deltaIndex*len(alphas) + alphaIndex
			group.Add(1)
			go func(index int, delta, alpha float64) {
				defer group.Done()
				slots <- struct{}{}
				defer func() { <-slots }()
				loads, elasticity, err := core.RunAllLoadsAndElasticityFast(configFor(alpha, delta, 5, ramp))
				if err != nil {
					fmt.Fprintln(os.Stderr, err)
					os.Exit(1)
				}
				observed := core.TrimWarmup(loads[0], core.StatWarmup)
				summary := core.SummarizeObservedLoadWindow(observed, targetLoad, convergenceTol, window)
				epsMin, epsMax := math.Inf(1), math.Inf(-1)
				for _, value := range elasticity[core.StatWarmup:] {
					epsMin = math.Min(epsMin, value)
					epsMax = math.Max(epsMax, value)
				}
				cells[index] = cell{delta: delta, alpha: alpha, summary: summary,
					epsMin: epsMin, epsMax: epsMax}
			}(index, delta, alpha)
		}
	}
	group.Wait()

	file, err := os.Create(output)
	if err != nil {
		return err
	}
	defer file.Close()
	writer := csv.NewWriter(file)
	_ = writer.Write([]string{"delta", "alpha_inflow", "distribution", "final_load",
		"avg_load", "load_std", "load_inflation", "converged", "full_block_fraction",
		"eps_min", "eps_max"})
	deltaSafe := math.Inf(1)
	maxInflation := math.Inf(-1)
	for _, item := range cells {
		_ = writer.Write([]string{
			format(item.delta), format(item.alpha), "Spike",
			format(item.summary.FinalLoad), format(item.summary.AverageLoad),
			format(item.summary.LoadStd), format(item.summary.LoadInflation),
			boolean(item.summary.Converged), format(item.summary.FullBlockFraction),
			format(item.epsMin), format(item.epsMax),
		})
		if !item.summary.Converged && item.delta < deltaSafe {
			deltaSafe = item.delta
		}
		maxInflation = math.Max(maxInflation, item.summary.LoadInflation)
	}
	writer.Flush()
	fmt.Printf("delta_safe=%.3f max_inflation=%.4f\n", deltaSafe, maxInflation)
	fmt.Printf("wrote %s (%d cells)\n", output, len(cells))
	return writer.Error()
}

// The 12 census bins of Figure 5, shared by both chains.
var edges = []float64{0, .02, .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.01}




func main() {
		shapeName := flag.String("shape", "", "log, linear, or logistic")
	workers := flag.Int("workers", runtime.NumCPU(), "concurrent trajectories")
	output := flag.String("output", "", "destination CSV")
	flag.Parse()

	ramp, err := shapeRamp(*shapeName)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if *output == "" {
		fmt.Fprintln(os.Stderr, "-output is required")
		os.Exit(1)
	}
	if err := os.MkdirAll(filepath.Dir(*output), 0o755); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	if err := runGrid(ramp, *workers, *output); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func format(value float64) string { return strconv.FormatFloat(value, 'g', -1, 64) }

func boolean(value bool) string {
	if value {
		return "True"
	}
	return "False"
}
