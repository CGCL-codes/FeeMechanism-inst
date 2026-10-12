package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"gas-for-multiple-shards/experiments/nonuniform"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := run(ctx, os.Args[1:], os.Stdout, os.Stderr); err != nil {
		fmt.Fprintf(os.Stderr, "nonuniform-2d: %v\n", err)
		os.Exit(1)
	}
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer) error {
	flags := flag.NewFlagSet("nonuniform-2d", flag.ContinueOnError)
	flags.SetOutput(stderr)
	outputDir := flags.String("output-dir", ".", "directory for the result CSV files")
	workers := flags.Int("workers", runtime.GOMAXPROCS(0), "number of concurrent nonlinear simulations")
	progressEvery := flags.Int("progress-every", 1000, "report progress every N completed points")
	jobFilter := flags.String("job", "all", "which job to run: grid-distinct, grid-chain0, random, or all")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("unexpected positional arguments: %v", flags.Args())
	}

	type job struct {
		name     string
		filename string
		points   []nonuniform.Point
	}
	jobs := []job{
		{"grid-distinct", "nonuniform_grid_distinct.csv", nonuniform.GridPoints(nonuniform.PerturbDistinct)},
		{"grid-chain0", "nonuniform_grid_chain0.csv", nonuniform.GridPoints(nonuniform.PerturbChainZero)},
		{"grid-chain0-125", "nonuniform_grid_chain0_125.csv", nonuniform.GridPointsCount(nonuniform.PerturbChainZero, 125)},
		{"grid-distinct-125", "nonuniform_grid_distinct_125.csv", nonuniform.GridPointsCount(nonuniform.PerturbDistinct, 125)},
		{"grid-uniform-125", "nonuniform_grid_uniform_125.csv", nonuniform.GridPointsCount(nonuniform.PerturbUniform, 125)},
		{"grid-chain1-125", "nonuniform_grid_chain1_125.csv", nonuniform.GridPointsCount(nonuniform.PerturbChainOne, 125)},
		{"grid-A-chain1-125", "nonuniform_grid_A_local20_125.csv", nonuniform.GridPointsTopology(nonuniform.PerturbChainOne, 125, nonuniform.TopologyLocal20)},
		{"grid-C-chain1-125", "nonuniform_grid_C_lambda16_125.csv", nonuniform.GridPointsTopology(nonuniform.PerturbChainOne, 125, nonuniform.TopologyLambda16)},
		{"random-125", "nonuniform_random_3d_125.csv", nonuniform.RandomPointsCount(nonuniform.PerturbDistinct, 125)},
		{"random-chain1-125", "nonuniform_random_3d_chain1_125.csv", nonuniform.RandomPointsCount(nonuniform.PerturbChainOne, 125)},
		{"grid3d", "nonuniform_grid3d_125.csv", nonuniform.Grid3DPoints(nonuniform.PerturbChainOne)},
		{"random", "nonuniform_random_3d.csv", nonuniform.RandomPoints(nonuniform.PerturbDistinct)},
	}

	for _, item := range jobs {
		if *jobFilter != "all" && *jobFilter != item.name {
			continue
		}
		started := time.Now()
		fmt.Fprintf(stdout, "Running %s: %d points, %d workers\n", item.name, len(item.points), *workers)
		results, err := nonuniform.Run(ctx, item.points, nonuniform.Options{
			Workers: *workers,
			Progress: func(done, total int) {
				if (*progressEvery > 0 && done%*progressEvery == 0) || done == total {
					elapsed := time.Since(started)
					rate := float64(done) / elapsed.Seconds()
					fmt.Fprintf(stderr, "%s: %d/%d (%.1f%%), %.1f points/s, elapsed %s\n",
						item.name, done, total, 100*float64(done)/float64(total), rate, elapsed.Round(time.Second))
				}
			},
		})
		if err != nil {
			return err
		}
		if err := nonuniform.WriteCSV(*outputDir, item.filename, results); err != nil {
			return err
		}
		fmt.Fprintf(stdout, "Completed %s in %s; wrote %d rows to %s/%s\n",
			item.name, time.Since(started).Round(time.Second), len(results), *outputDir, item.filename)
	}
	return nil
}
