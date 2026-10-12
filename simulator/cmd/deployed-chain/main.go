package main

import (
	"flag"
	"fmt"
	"gas-for-multiple-shards/core"
	"log"
	"os"
	"strconv"
	"strings"
)

var mempoolCap = flag.Float64("mempool", 20,
	"per-chain transaction pool bound, in multiples of the block gas limit (0 disables the bound)")

var totalSteps = flag.Int("total-steps", 50100,
	"simulated horizon in blocks, including the 100 pre-shock blocks")

// delayWeights, when non-empty, replaces the spike distribution with the given
// comma-separated weights for delays 1..len(weights). They are normalized here.
var delayWeights = flag.String("weights", "",
	"comma-separated delay weights for d=1..n, overriding the spike at dmax")

func parseWeights() []float64 {
	if *delayWeights == "" {
		return nil
	}
	parts := strings.Split(*delayWeights, ",")
	weights := make([]float64, len(parts))
	sum := 0.0
	for i, p := range parts {
		v, err := strconv.ParseFloat(strings.TrimSpace(p), 64)
		if err != nil {
			log.Fatal(err)
		}
		weights[i] = v
		sum += v
	}
	for i := range weights {
		weights[i] /= sum
	}
	return weights
}

func configFor(alpha, delta float64, dmax int) core.Config {
	target := 1_000_000.0
	in0 := target * alpha
	diag := target - in0
	cross := in0 / 4
	weights := parseWeights()
	if weights == nil {
		weights = make([]float64, dmax)
		weights[dmax-1] = 1
	}
	dmax = len(weights)
	return core.Config{
		Simulation: core.SimulationConfig{
			TotalSteps: *totalSteps, LTarget: 0.5, Delta: delta,
			MempoolCap:   *mempoolCap,
			Perturbation: core.PerturbationConfig{Enabled: false},
			DemandShock: core.DemandShockConfig{
				Enabled: true, StartStep: 100, EndStep: 101,
				Multiplier: 1.01, TargetShards: []int{0},
			},
		},
		Network: core.NetworkConfig{NumShards: 3},
		Shards: []core.ShardSpec{
			{ID: 0, GMax: 2_000_000}, {ID: 1, GMax: 2_000_000}, {ID: 2, GMax: 2_000_000},
		},
		Demand: core.DemandConfig{
			BaseDemandMatrix: [][]float64{
				{diag, 0, 0}, {in0 / 2, diag, cross}, {in0 / 2, cross, diag},
			},
			LambdaMatrix:  [][]float64{{1.5, 1.5, 1.5}, {1.5, 1.5, 1.5}, {1.5, 1.5, 1.5}},
			EpsilonMatrix: [][]float64{{0, 1.5, 1.5}, {16, 0, 1.5}, {16, 1.5, 0}},
		},
		Delay: core.DelayConfig{MaxDelay: dmax, Weights: weights},
	}
}

func main() {
	flag.Parse()
	args := flag.Args()
	var alpha float64
	var dmax int
	var deployed float64
	fmt.Sscanf(args[0], "%f", &alpha)
	fmt.Sscanf(args[1], "%d", &dmax)
	fmt.Sscanf(args[2], "%f", &deployed)
	maxStable, firstUnstable := -1.0, -1.0
	for i := 1; i <= 300; i++ {
		d := float64(i) / 1000
		s, err := core.RunObservedLoadSummaryFastWindow(configFor(alpha, d, dmax), 0, 0.5, 0.0005, 50, core.StatWarmup)
		if err != nil {
			log.Fatal(err)
		}
		if s.Converged {
			if d > maxStable {
				maxStable = d
			}
		} else if firstUnstable < 0 {
			firstUnstable = d
		}
	}
	fmt.Printf("alpha=%.3f spike d=%d: max stable delta=%.3f first unstable=%.3f\n",
		alpha, dmax, maxStable, firstUnstable)
	loads, err := core.RunObservedLoadFast(configFor(alpha, deployed, dmax), 0)
	if err != nil {
		log.Fatal(err)
	}
	f, _ := os.Create(args[3])
	fmt.Fprintln(f, "slot,load")
	sumPost := 0.0
	for i, v := range loads {
		if i >= core.StatWarmup {
			sumPost += v
			fmt.Fprintf(f, "%d,%.17g\n", i-core.StatWarmup, v)
		}
	}
	f.Close()
	post := float64(len(loads) - core.StatWarmup)
	fmt.Printf("deployed delta: inflation(post-warmup)=%.2f%%  mean(post-warmup)=%.4f\n",
		(sumPost/post/0.5-1)*100, sumPost/post)
}
