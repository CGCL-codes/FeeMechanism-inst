package main

import (
	"flag"
	"fmt"
	"gas-for-multiple-shards/core"
	"log"
	"math/rand"
	"os"
	"runtime"
	"strconv"
	"sync"
)

var edges = []float64{0, .02, .05, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.01}

var mempoolCap = flag.Float64("mempool", 20,
	"per-chain transaction pool bound, in multiples of the block gas limit (0 disables the bound)")

var totalSteps = flag.Int("total-steps", 50100,
	"simulated horizon in blocks, including the 100 pre-shock blocks")

// binScale multiplies every census-bin edge except the terminal one. Emitting
// counts over edges r*e implements the GasWanted conversion declared =
// min(load/r, 1): a load lands in converted bin j exactly when it lies in
// [r*e_j, r*e_{j+1}).
var binScale = flag.Float64("binscale", 1.0,
	"scale factor applied to the census bin edges (the GasUsed-to-GasWanted ratio)")

// uniformBins, when positive, replaces the census edges with that many equal
// bins over [0, 1], so the same sweep can be scored at any mapping resolution.
var uniformBins = flag.Int("uniform-bins", 0,
	"emit this many equal-width bins over [0,1] instead of the census edges")

func configFor(eps, alpha, delta float64) core.Config {
	target := 1_000_000.0
	in0 := target * alpha
	diag := target - in0
	cross := in0 / 4
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
			EpsilonMatrix: [][]float64{{0, 1.5, 1.5}, {eps, 0, 1.5}, {eps, 1.5, 0}},
		},
		Delay: core.DelayConfig{MaxDelay: 5, Weights: []float64{0, 0, 0, 0, 1}},
	}
}

func main() {
	flag.Parse()
	args := flag.Args()
	if len(args) < 3 {
		log.Fatal("usage: random-sample [-mempool Q] <out.csv> <n_draws> <seed>")
	}
	n, _ := strconv.Atoi(args[1])
	seed, _ := strconv.ParseInt(args[2], 10, 64)
	var fileDraws [][3]float64
	if args[1] == "-file" {
		f, err := os.Open(args[2])
		if err != nil {
			log.Fatal(err)
		}
		var e, a, d float64
		for {
			k, _ := fmt.Fscanf(f, "%g,%g,%g\n", &e, &a, &d)
			if k < 3 {
				break
			}
			fileDraws = append(fileDraws, [3]float64{e, a, d})
		}
		f.Close()
		n = len(fileDraws)
	}

	epsLo, epsHi, aLo, aHi, dLo, dHi := 0.0, 16.0, 0.01, 0.99, 0.001, 0.125
	if len(args) >= 9 {
		pf := func(s string) float64 { v, _ := strconv.ParseFloat(s, 64); return v }
		epsLo, epsHi = pf(args[3]), pf(args[4])
		aLo, aHi = pf(args[5]), pf(args[6])
		dLo, dHi = pf(args[7]), pf(args[8])
	}
	binEdges := make([]float64, len(edges))
	copy(binEdges, edges)
	if *uniformBins > 0 {
		binEdges = make([]float64, *uniformBins+1)
		for i := 0; i <= *uniformBins; i++ {
			binEdges[i] = float64(i) / float64(*uniformBins)
		}
		binEdges[*uniformBins] = 1.01
	}
	for i := 0; i < len(binEdges)-1; i++ {
		binEdges[i] *= *binScale
	}
	rng := rand.New(rand.NewSource(seed))
	type draw struct{ eps, alpha, delta float64 }
	draws := make([]draw, n)
	if fileDraws != nil {
		for i, t := range fileDraws {
			draws[i] = draw{eps: t[0], alpha: t[1], delta: t[2]}
		}
	} else {
		for i := range draws {
			draws[i] = draw{
				eps:   epsLo + rng.Float64()*(epsHi-epsLo),
				alpha: aLo + rng.Float64()*(aHi-aLo),
				delta: dLo + rng.Float64()*(dHi-dLo),
			}
		}
	}
	out := make([]string, n)
	var wg sync.WaitGroup
	sem := make(chan struct{}, runtime.NumCPU()-1)
	var mu sync.Mutex
	done := 0
	for i, d := range draws {
		wg.Add(1)
		go func(i int, d draw) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			loads, err := core.RunObservedLoadFast(configFor(d.eps, d.alpha, d.delta), 0)
			if err != nil {
				log.Fatal(err)
			}
			post := 0.0
			for _, v := range loads[core.StatWarmup:] {
				post += v
			}
			postSteps := float64(len(loads) - core.StatWarmup)
			counts := make([]int, len(binEdges)-1)
			for _, v := range loads[core.StatWarmup:] {
				if v < 0 {
					v = 0
				}
				if v > 1 {
					v = 1
				}
				for b := 0; b < len(binEdges)-1; b++ {
					if v >= binEdges[b] && v < binEdges[b+1] {
						counts[b]++
						break
					}
				}
			}
			row := fmt.Sprintf("%.6f,%.6f,%.6f,%.4f", d.eps, d.alpha, d.delta,
				(post/postSteps/0.5-1)*100)
			for _, c := range counts {
				row += fmt.Sprintf(",%d", c)
			}
			out[i] = row
			mu.Lock()
			done++
			if done%500 == 0 {
				fmt.Fprintf(os.Stderr, "%d/%d\n", done, n)
			}
			mu.Unlock()
		}(i, d)
	}
	wg.Wait()
	f, err := os.Create(args[0])
	if err != nil {
		log.Fatal(err)
	}
	hdr := "eps,alpha,delta,inflation_pct"
	for b := 0; b < len(binEdges)-1; b++ {
		hdr += fmt.Sprintf(",bin%d", b)
	}
	fmt.Fprintln(f, hdr)
	for _, r := range out {
		fmt.Fprintln(f, r)
	}
	f.Close()
	fmt.Printf("wrote %d draws\n", n)
}
