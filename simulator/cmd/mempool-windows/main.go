// segments walks one Figure 4a cell block by block and reports the load
// statistics over consecutive windows, so a post-shock transient can be told
// apart from the phase jitter of a window that ends mid-cycle.
package main

import (
	"flag"
	"fmt"
	"math"

	"gas-for-multiple-shards/core"
	"gas-for-multiple-shards/experiments/boundary"
)

func main() {
	eps := flag.Float64("eps", 9.8, "epsilon_j0")
	alpha := flag.Float64("alpha", 0.99, "inbound ratio")
	steps := flag.Int("total-steps", 1000100, "horizon")
	seg := flag.Int("segment", 25000, "segment length in blocks")
	flag.Parse()

	fmt.Printf("cell eps=%g alpha=%g, horizon %d, segment %d\n", *eps, *alpha, *steps, *seg)
	fmt.Printf("%-4s %-22s %-11s %-11s %-11s %-11s\n",
		"Q", "segment", "seg infl%", "seg %full", "cum infl%", "cum %full")

	for _, q := range []float64{20, 100} {
		boundary.MempoolCap = q
		boundary.TotalSteps = *steps
		point := boundary.Point{Figure: boundary.Figure6, Distribution: boundary.Spike,
			Parameter: *eps, Alpha: *alpha}
		config, err := boundary.ConfigFor(point)
		if err != nil {
			panic(err)
		}
		loads, err := core.RunObservedLoadFast(config, 0)
		if err != nil {
			panic(err)
		}
		loads = core.TrimWarmup(loads, core.StatWarmup)

		cumSum, cumFull := 0.0, 0
		for start := 0; start < len(loads); start += *seg {
			end := start + *seg
			if end > len(loads) {
				end = len(loads)
			}
			sum, full := 0.0, 0
			for _, load := range loads[start:end] {
				sum += load
				if load >= 1-1e-9 {
					full++
				}
			}
			n := end - start
			cumSum += sum
			cumFull += full
			fmt.Printf("%-4g %-22s %-11.4f %-11.4f %-11.4f %-11.4f\n",
				q, fmt.Sprintf("[%d,%d)", start, end),
				100*((sum/float64(n))-0.5)/0.5, 100*float64(full)/float64(n),
				100*((cumSum/float64(end))-0.5)/0.5, 100*float64(cumFull)/float64(end))
		}
		_ = math.Abs
	}
}
