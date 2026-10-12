// mempool-check evaluates individual boundary-sweep points at a chosen
// transaction-pool bound. It exists so that a single (epsilon, alpha) cell can
// be inspected without rerunning the full sweep, and so that the unbounded case
// can be checked against the published CSVs.
package main

import (
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"

	"gas-for-multiple-shards/core"
	"gas-for-multiple-shards/experiments/boundary"
)

func main() {
	figureValue := flag.String("figure", "fig4a", "fig4a or fig4c")
	distribution := flag.String("dist", "Spike", "Spike, Uniform, or Bimodal")
	mempool := flag.Float64("mempool", 20, "pool bound in block gas limits (0 disables)")
	pointList := flag.String("points", "", "comma-separated parameter:alpha pairs, e.g. 16:0.99,3.1:0.97")
	steps := flag.Int("steps", 0, "override the 50,100-block horizon (0 keeps the sweep default)")
	flag.Parse()

	figure, err := boundary.ParseFigure(*figureValue)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	boundary.MempoolCap = *mempool

	fmt.Printf("%10s %8s %14s %14s %10s %10s\n",
		"parameter", "alpha", "avg_load", "inflation", "full%", "converged")
	for _, pair := range strings.Split(*pointList, ",") {
		pair = strings.TrimSpace(pair)
		if pair == "" {
			continue
		}
		fields := strings.SplitN(pair, ":", 2)
		if len(fields) != 2 {
			fmt.Fprintf(os.Stderr, "bad point %q\n", pair)
			os.Exit(1)
		}
		parameter, err := strconv.ParseFloat(fields[0], 64)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		alpha, err := strconv.ParseFloat(fields[1], 64)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		point := boundary.Point{
			Figure:       figure,
			Distribution: boundary.Distribution(*distribution),
			Parameter:    parameter,
			Alpha:        alpha,
		}
		config, err := boundary.ConfigFor(point)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		if *steps > 0 {
			config.Simulation.TotalSteps = *steps
		}
		summary, err := core.RunObservedLoadSummaryFastWindow(config, 0, 0.5, 0.5*1e-3, 50, core.StatWarmup)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		fmt.Printf("%10g %8g %14.10f %14.10f %9.2f%% %10v\n",
			parameter, alpha, summary.AverageLoad, summary.LoadInflation,
			100*summary.FullBlockFraction, summary.Converged)
	}
}
