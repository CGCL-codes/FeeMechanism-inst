// Package mitigation reruns the Figure 4 grids under the compensated
// EIP-1559 controller of Appendix D, and scans the calibration error of the
// compensation gain.
package mitigation

import (
	"context"
	"encoding/csv"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"sync"

	"gas-for-multiple-shards/core"
	"gas-for-multiple-shards/experiments/boundary"
)

const (
	targetLoad         = 0.5
	relativeTolerance  = 1e-3
	absoluteTolerance  = targetLoad * relativeTolerance
	convergenceWindow  = 50
	observedShard      = 0
)

// Mode selects which grid to sweep.
type Mode string

const (
	// ModeFig4a reruns the (epsilon_j0, alpha) grid at delta = 0.125.
	ModeFig4a Mode = "fig4a"
	// ModeFig4c reruns the (delta, alpha) grid at epsilon_j0 = 16, the Figure 4c grid.
	ModeFig4c Mode = "fig4c"
	// ModeGamma scans the calibration factor gamma of the compensation gain
	// against delta, at the hardest corner alpha = 0.99, epsilon_j0 = 16.
	ModeGamma Mode = "gamma"
)

// Point is one grid point. Gamma scales the exact compensation gain, so
// Gamma = 0 reproduces plain EIP-1559 and Gamma = 1 is exact compensation.
type Point struct {
	Index     int
	Mode      Mode
	Parameter float64
	Alpha     float64
	Gamma     float64
}

type Result struct {
	Point         Point
	Summary       core.ObservedLoadSummary
	Compensations []float64
}

type Options struct {
	Workers  int
	Progress func(done, total int)
}

func ParseMode(value string) (Mode, error) {
	mode := Mode(value)
	switch mode {
	case ModeFig4a, ModeFig4c, ModeGamma:
		return mode, nil
	default:
		return "", errors.New("mode must be fig4a, fig4c, or gamma")
	}
}

// Points enumerates the same grids as the Figure 4 sweep. Figure 4a walks
// epsilon_j0 over [0, 16] at step 0.1 and Figure 4b walks delta over
// [0.001, 0.125] at step 0.001, both against alpha over [0.01, 0.99] at
// step 0.01. The gamma scan walks gamma over [0, 1.5] at step 0.005 against
// the same delta grid.
func Points(mode Mode) []Point {
	points := make([]Point, 0, 16000)
	switch mode {
	case ModeFig4a:
		for parameterIndex := 160; parameterIndex >= 0; parameterIndex-- {
			for alphaIndex := 99; alphaIndex >= 1; alphaIndex-- {
				points = append(points, Point{
					Index:     len(points),
					Mode:      mode,
					Parameter: float64(parameterIndex) / 10,
					Alpha:     float64(alphaIndex) / 100,
					Gamma:     1,
				})
			}
		}
	case ModeFig4c:
		for parameterIndex := 124; parameterIndex >= 0; parameterIndex-- {
			for alphaIndex := 99; alphaIndex >= 1; alphaIndex-- {
				points = append(points, Point{
					Index:     len(points),
					Mode:      mode,
					Parameter: float64(parameterIndex+1) / 1000,
					Alpha:     float64(alphaIndex) / 100,
					Gamma:     1,
				})
			}
		}
	case ModeGamma:
		for parameterIndex := 199; parameterIndex >= 0; parameterIndex-- {
			for gammaIndex := 300; gammaIndex >= 0; gammaIndex-- {
				points = append(points, Point{
					Index:     len(points),
					Mode:      mode,
					Parameter: float64(parameterIndex+1) / 1000,
					Alpha:     0.99,
					Gamma:     float64(gammaIndex) / 200,
				})
			}
		}
	}
	return points
}

// ConfigFor builds the Figure 4 configuration and attaches the compensation
// gains. The base topology, elasticities, shock, and latency are taken
// unchanged from the Figure 4 sweep, so the only difference is the controller.
func ConfigFor(point Point) (core.Config, error) {
	boundaryPoint := boundary.Point{
		Distribution: boundary.Spike,
		Alpha:        point.Alpha,
	}
	// The gamma scan walks delta past the Figure 4b grid, so it builds the
	// topology at the deployed rate and then overrides delta.
	overrideDelta := 0.0
	switch point.Mode {
	case ModeFig4a:
		boundaryPoint.Figure = boundary.Figure6
		boundaryPoint.Parameter = point.Parameter
	case ModeFig4c:
		boundaryPoint.Figure = boundary.Figure7
		boundaryPoint.Parameter = point.Parameter
	case ModeGamma:
		boundaryPoint.Figure = boundary.Figure7
		boundaryPoint.Parameter = 0.125
		overrideDelta = point.Parameter
	default:
		return core.Config{}, fmt.Errorf("unknown mode %q", point.Mode)
	}

	config, err := boundary.ConfigFor(boundaryPoint)
	if err != nil {
		return core.Config{}, err
	}
	if overrideDelta > 0 {
		config.Simulation.Delta = overrideDelta
	}
	if point.Gamma < 0 {
		return core.Config{}, fmt.Errorf("gamma %g must be nonnegative", point.Gamma)
	}
	gains := core.ExactCompensationPerShard(&config)
	for shardID := range gains {
		gains[shardID] *= point.Gamma
	}
	config.Simulation.CompensationPerShard = gains
	return config, nil
}

func Run(ctx context.Context, points []Point, options Options) ([]Result, error) {
	if len(points) == 0 {
		return []Result{}, nil
	}
	workers := options.Workers
	if workers <= 0 {
		workers = runtime.GOMAXPROCS(0)
	}
	if workers > len(points) {
		workers = len(points)
	}

	runContext, cancel := context.WithCancel(ctx)
	defer cancel()
	type outcome struct {
		result Result
		err    error
	}
	jobs := make(chan Point)
	outcomes := make(chan outcome, workers)

	var workerGroup sync.WaitGroup
	workerGroup.Add(workers)
	for worker := 0; worker < workers; worker++ {
		go func() {
			defer workerGroup.Done()
			for point := range jobs {
				result, err := evaluate(runContext, point)
				if err != nil {
					outcomes <- outcome{err: fmt.Errorf("%s parameter=%g alpha=%g gamma=%g: %w",
						point.Mode, point.Parameter, point.Alpha, point.Gamma, err)}
					cancel()
					return
				}
				outcomes <- outcome{result: result}
			}
		}()
	}

	go func() {
		defer close(jobs)
		for _, point := range points {
			select {
			case jobs <- point:
			case <-runContext.Done():
				return
			}
		}
	}()
	go func() {
		workerGroup.Wait()
		close(outcomes)
	}()

	results := make([]Result, 0, len(points))
	var firstError error
	done := 0
	for outcome := range outcomes {
		done++
		if options.Progress != nil {
			options.Progress(done, len(points))
		}
		if outcome.err != nil {
			if firstError == nil {
				firstError = outcome.err
			}
			continue
		}
		results = append(results, outcome.result)
	}
	if firstError != nil {
		return nil, firstError
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if len(results) != len(points) {
		return nil, fmt.Errorf("sweep completed %d of %d points", len(results), len(points))
	}
	sort.Slice(results, func(i, j int) bool {
		return results[i].Point.Index < results[j].Point.Index
	})
	return results, nil
}

func evaluate(ctx context.Context, point Point) (Result, error) {
	if err := ctx.Err(); err != nil {
		return Result{}, err
	}
	config, err := ConfigFor(point)
	if err != nil {
		return Result{}, err
	}
	summary, err := core.RunObservedLoadSummaryFastWindow(
		config, observedShard, targetLoad, absoluteTolerance, convergenceWindow, core.StatWarmup)
	if err != nil {
		return Result{}, err
	}
	if err := ctx.Err(); err != nil {
		return Result{}, err
	}
	return Result{
		Point:         point,
		Summary:       summary,
		Compensations: config.Simulation.CompensationPerShard,
	}, nil
}

func WriteCSV(outputDir string, mode Mode, results []Result) error {
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return fmt.Errorf("create output directory: %w", err)
	}
	filename := fmt.Sprintf("mitigation_%s_Spike.csv", mode)
	parameterHeader := "epsilon_j0"
	if mode != ModeFig4a {
		parameterHeader = "delta"
	}
	finalPath := filepath.Join(outputDir, filename)

	temporary, err := os.CreateTemp(outputDir, "."+filename+".*.tmp")
	if err != nil {
		return fmt.Errorf("create temporary CSV: %w", err)
	}
	temporaryPath := temporary.Name()
	committed := false
	defer func() {
		if !committed {
			_ = os.Remove(temporaryPath)
		}
	}()

	writer := csv.NewWriter(temporary)
	header := []string{parameterHeader, "alpha_inflow", "gamma", "compensation_h0",
		"distribution", "final_load", "avg_load", "load_std", "load_inflation", "converged",
		"full_block_fraction"}
	if err := writer.Write(header); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("write header: %w", err)
	}
	for _, result := range results {
		gain := 0.0
		if len(result.Compensations) > 0 {
			gain = result.Compensations[0]
		}
		record := []string{
			formatFloat(result.Point.Parameter),
			formatFloat(result.Point.Alpha),
			formatFloat(result.Point.Gamma),
			formatFloat(gain),
			"Spike",
			formatFloat(result.Summary.FinalLoad),
			formatFloat(result.Summary.AverageLoad),
			formatFloat(result.Summary.LoadStd),
			formatFloat(result.Summary.LoadInflation),
			formatBool(result.Summary.Converged),
			formatFloat(result.Summary.FullBlockFraction),
		}
		if err := writer.Write(record); err != nil {
			_ = temporary.Close()
			return fmt.Errorf("write row %d: %w", result.Point.Index, err)
		}
	}
	writer.Flush()
	if err := writer.Error(); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("flush: %w", err)
	}
	if err := temporary.Sync(); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("sync: %w", err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("close: %w", err)
	}
	if err := os.Rename(temporaryPath, finalPath); err != nil {
		return fmt.Errorf("replace %s: %w", finalPath, err)
	}
	committed = true
	return nil
}

func formatFloat(value float64) string {
	return strconv.FormatFloat(value, 'g', -1, 64)
}

func formatBool(value bool) string {
	if value {
		return "True"
	}
	return "False"
}
