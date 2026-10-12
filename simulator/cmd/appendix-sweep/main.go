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

	"gas-for-multiple-shards/experiments/appendix"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := run(ctx, os.Args[1:], os.Stdout, os.Stderr); err != nil {
		fmt.Fprintf(os.Stderr, "appendix-sweep: %v\n", err)
		os.Exit(1)
	}
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer) error {
	flags := flag.NewFlagSet("appendix-sweep", flag.ContinueOnError)
	flags.SetOutput(stderr)
	figureValue := flags.String("figure", "", "experiment to run: fig9-top, fig9-bottom, fig10, fig12, or fig13")
	outputDir := flags.String("output-dir", ".", "directory for result CSV files")
	workers := flags.Int("workers", runtime.GOMAXPROCS(0), "number of concurrent nonlinear simulations")
	progressEvery := flags.Int("progress-every", 500, "report progress every N completed points (0 disables intermediate reports)")
	mempool := flags.Float64("mempool", appendix.MempoolCap, "per-chain transaction pool bound, in multiples of the block gas limit (0 disables the bound)")
	totalSteps := flags.Int("total-steps", appendix.TotalSteps, "simulated horizon in blocks, including the 100 pre-shock blocks")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *mempool < 0 {
		return fmt.Errorf("mempool cannot be negative")
	}
	if *totalSteps <= 0 {
		return fmt.Errorf("total-steps must be positive")
	}
	appendix.MempoolCap = *mempool
	appendix.TotalSteps = *totalSteps
	if flags.NArg() != 0 {
		return fmt.Errorf("unexpected positional arguments: %v", flags.Args())
	}
	figure, err := appendix.ParseFigure(*figureValue)
	if err != nil {
		return err
	}
	if *workers < 1 {
		return fmt.Errorf("workers must be at least 1")
	}
	if *progressEvery < 0 {
		return fmt.Errorf("progress-every cannot be negative")
	}

	points := appendix.Points(figure)
	started := time.Now()
	fmt.Fprintf(stdout, "Running %s: %d points, %d workers, shock=[100,101), multiplier=1.01, total_steps=%d, mempool=%g\n", *figureValue, len(points), *workers, *totalSteps, *mempool)
	results, err := appendix.Run(ctx, points, appendix.Options{
		Workers: *workers,
		Progress: func(done, total int) {
			if (*progressEvery > 0 && done%*progressEvery == 0) || done == total {
				elapsed := time.Since(started)
				rate := float64(done) / elapsed.Seconds()
				fmt.Fprintf(stderr, "progress: %d/%d (%.1f%%), %.1f points/s, elapsed %s\n",
					done, total, 100*float64(done)/float64(total), rate, elapsed.Round(time.Second))
			}
		},
	})
	if err != nil {
		return err
	}
	if err := appendix.WriteCSVs(*outputDir, figure, results); err != nil {
		return err
	}
	fmt.Fprintf(stdout, "Completed %s in %s; wrote %d deterministic rows to %s\n",
		*figureValue, time.Since(started).Round(time.Second), len(results), *outputDir)
	return nil
}
