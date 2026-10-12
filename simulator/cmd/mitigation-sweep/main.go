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

	"gas-for-multiple-shards/experiments/boundary"
	"gas-for-multiple-shards/experiments/mitigation"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := run(ctx, os.Args[1:], os.Stdout, os.Stderr); err != nil {
		fmt.Fprintf(os.Stderr, "mitigation-sweep: %v\n", err)
		os.Exit(1)
	}
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer) error {
	flags := flag.NewFlagSet("mitigation-sweep", flag.ContinueOnError)
	flags.SetOutput(stderr)
	modeValue := flags.String("mode", "", "grid to sweep: fig4a, fig4c, or gamma")
	outputDir := flags.String("output-dir", ".", "directory for the result CSV")
	workers := flags.Int("workers", runtime.GOMAXPROCS(0), "number of concurrent nonlinear simulations")
	progressEvery := flags.Int("progress-every", 500, "report progress every N completed points (0 disables)")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("unexpected positional arguments: %v", flags.Args())
	}
	mode, err := mitigation.ParseMode(*modeValue)
	if err != nil {
		return err
	}
	if *workers < 1 {
		return fmt.Errorf("workers must be at least 1")
	}
	if *progressEvery < 0 {
		return fmt.Errorf("progress-every cannot be negative")
	}

	points := mitigation.Points(mode)
	started := time.Now()
	fmt.Fprintf(stdout, "Running %s: %d points, %d workers, spike latency, shock=[100,101), multiplier=1.01, total_steps=%d, mempool=%g\n",
		mode, len(points), *workers, boundary.TotalSteps, boundary.MempoolCap)
	results, err := mitigation.Run(ctx, points, mitigation.Options{
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
	if err := mitigation.WriteCSV(*outputDir, mode, results); err != nil {
		return err
	}
	fmt.Fprintf(stdout, "Completed %s in %s; wrote %d deterministic rows to %s\n",
		mode, time.Since(started).Round(time.Second), len(results), *outputDir)
	return nil
}
