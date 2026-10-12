package boundary

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
)

type Figure string

const (
	Figure6 Figure = "fig6"
	Figure7 Figure = "fig7"
)

type Distribution string

const (
	Spike   Distribution = "Spike"
	Uniform Distribution = "Uniform"
	Bimodal Distribution = "Bimodal"
)

var distributions = []Distribution{Spike, Uniform, Bimodal}

const (
	boundaryTargetLoad                    = 0.5
	relativeFinalLoadConvergenceTolerance = 1e-3
	absoluteFinalLoadConvergenceTolerance = boundaryTargetLoad * relativeFinalLoadConvergenceTolerance
	boundaryConvergenceWindow             = 50
)

// MempoolCap is each chain's transaction-pool bound, in multiples of the block
// gas limit. The default of 20 follows the default pool sizes of geth,
// CometBFT, and Substrate. Setting it to zero restores an unbounded pool.
var MempoolCap = 20.0

// TotalSteps is the simulated horizon. The first core.StatWarmup blocks precede
// the demand shock and are excluded from the load statistics, so the default
// leaves 50,000 post-shock blocks.
var TotalSteps = 50100

type Point struct {
	Index        int
	Figure       Figure
	Distribution Distribution
	Parameter    float64
	Alpha        float64
}

type Result struct {
	Point   Point
	Summary core.ObservedLoadSummary
}

type Evaluator func(context.Context, Point) (core.ObservedLoadSummary, error)

type Options struct {
	Workers   int
	Evaluator Evaluator
	Progress  func(done, total int)
}

func Points(figure Figure) []Point {
	var parameterCount int
	switch figure {
	case Figure6:
		parameterCount = 161
	case Figure7:
		parameterCount = 125
	default:
		return nil
	}

	points := make([]Point, 0, len(distributions)*parameterCount*99)
	for _, distribution := range distributions {
		for primaryIndex := parameterCount - 1; primaryIndex >= 0; primaryIndex-- {
			parameter := float64(primaryIndex) / 10
			if figure == Figure7 {
				parameter = float64(primaryIndex+1) / 1000
			}
			for alphaIndex := 99; alphaIndex >= 1; alphaIndex-- {
				points = append(points, Point{
					Index:        len(points),
					Figure:       figure,
					Distribution: distribution,
					Parameter:    parameter,
					Alpha:        float64(alphaIndex) / 100,
				})
			}
		}
	}
	return points
}

func ConfigFor(point Point) (core.Config, error) {
	weights, err := delayWeights(point.Distribution)
	if err != nil {
		return core.Config{}, err
	}
	if point.Alpha < 0.01 || point.Alpha > 0.99 {
		return core.Config{}, fmt.Errorf("alpha %g is outside [0.01, 0.99]", point.Alpha)
	}

	delta := 0.125
	inboundElasticity := point.Parameter
	switch point.Figure {
	case Figure6:
		if point.Parameter < 0 || point.Parameter > 16 {
			return core.Config{}, fmt.Errorf("Figure 6 epsilon %g is outside [0, 16]", point.Parameter)
		}
	case Figure7:
		if point.Parameter < 0.001 || point.Parameter > 0.125 {
			return core.Config{}, fmt.Errorf("Figure 7 delta %g is outside [0.001, 0.125]", point.Parameter)
		}
		delta = point.Parameter
		inboundElasticity = 16
	default:
		return core.Config{}, fmt.Errorf("unknown figure %q", point.Figure)
	}

	demand := demandMatrix(point.Alpha)
	return core.Config{
		Simulation: core.SimulationConfig{
			TotalSteps: TotalSteps,
			LTarget:    0.5,
			Delta:      delta,
			MempoolCap: MempoolCap,
			Perturbation: core.PerturbationConfig{
				Enabled: false,
			},
			DemandShock: core.DemandShockConfig{
				Enabled:      true,
				StartStep:    100,
				EndStep:      101,
				Multiplier:   1.01,
				TargetShards: []int{0},
			},
		},
		Network: core.NetworkConfig{NumShards: 3},
		Shards: []core.ShardSpec{
			{ID: 0, GMax: 2_000_000},
			{ID: 1, GMax: 2_000_000},
			{ID: 2, GMax: 2_000_000},
		},
		Demand: core.DemandConfig{
			BaseDemandMatrix: demand,
			LambdaMatrix: [][]float64{
				{1.5, 1.5, 1.5},
				{1.5, 1.5, 1.5},
				{1.5, 1.5, 1.5},
			},
			EpsilonMatrix: [][]float64{
				{0, 1.5, 1.5},
				{inboundElasticity, 0, 1.5},
				{inboundElasticity, 1.5, 0},
			},
		},
		Delay: core.DelayConfig{MaxDelay: 5, Weights: weights},
	}, nil
}

func delayWeights(distribution Distribution) ([]float64, error) {
	switch distribution {
	case Spike:
		return []float64{0, 0, 0, 0, 1}, nil
	case Uniform:
		return []float64{0.2, 0.2, 0.2, 0.2, 0.2}, nil
	case Bimodal:
		return []float64{0.4, 0, 0.2, 0, 0.4}, nil
	default:
		return nil, fmt.Errorf("unknown delay distribution %q", distribution)
	}
}

func demandMatrix(alpha float64) [][]float64 {

	targetDemand := 1_000_000.0
	inboundToZero := targetDemand * alpha
	diagonal := targetDemand - inboundToZero
	crossBetweenSources := inboundToZero / 4
	return [][]float64{
		{diagonal, 0, 0},
		{inboundToZero / 2, diagonal, crossBetweenSources},
		{inboundToZero / 2, crossBetweenSources, diagonal},
	}
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
	evaluator := options.Evaluator
	if evaluator == nil {
		evaluator = evaluatePoint
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
				summary, err := evaluator(runContext, point)
				if err != nil {
					outcomes <- outcome{err: fmt.Errorf("%s %s parameter=%g alpha=%g: %w", point.Figure, point.Distribution, point.Parameter, point.Alpha, err)}
					cancel()
					return
				}
				outcomes <- outcome{result: Result{Point: point, Summary: summary}}
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

			if firstError == nil || (isContextError(firstError) && !isContextError(outcome.err)) {
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

func isContextError(err error) bool {
	return errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded)
}

func evaluatePoint(ctx context.Context, point Point) (core.ObservedLoadSummary, error) {
	if err := ctx.Err(); err != nil {
		return core.ObservedLoadSummary{}, err
	}
	config, err := ConfigFor(point)
	if err != nil {
		return core.ObservedLoadSummary{}, err
	}
	summary, err := core.RunObservedLoadSummaryFastWindow(
		config,
		0,
		boundaryTargetLoad,
		absoluteFinalLoadConvergenceTolerance,
		boundaryConvergenceWindow,
		core.StatWarmup,
	)
	if err != nil {
		return core.ObservedLoadSummary{}, err
	}
	if err := ctx.Err(); err != nil {
		return core.ObservedLoadSummary{}, err
	}
	return summary, nil
}

func WriteCSVs(outputDir string, figure Figure, results []Result) error {
	if figure != Figure6 && figure != Figure7 {
		return fmt.Errorf("unknown figure %q", figure)
	}
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return fmt.Errorf("create output directory: %w", err)
	}

	grouped := make(map[Distribution][]Result)
	for _, result := range results {
		if result.Point.Figure != figure {
			return fmt.Errorf("result %d belongs to %s, not %s", result.Point.Index, result.Point.Figure, figure)
		}
		grouped[result.Point.Distribution] = append(grouped[result.Point.Distribution], result)
	}
	for _, distribution := range distributions {
		distributionResults := grouped[distribution]
		if len(distributionResults) == 0 {
			continue
		}
		sort.Slice(distributionResults, func(i, j int) bool {
			return distributionResults[i].Point.Index < distributionResults[j].Point.Index
		})
		if err := writeDistributionCSV(outputDir, figure, distribution, distributionResults); err != nil {
			return err
		}
	}
	return nil
}

func writeDistributionCSV(outputDir string, figure Figure, distribution Distribution, results []Result) error {
	filename := fmt.Sprintf("convergence_results_%s.csv", distribution)
	parameterHeader := "epsilon_j0"
	if figure == Figure7 {
		filename = fmt.Sprintf("convergence_results_delta_%s.csv", distribution)
		parameterHeader = "delta"
	}
	finalPath := filepath.Join(outputDir, filename)
	temporary, err := os.CreateTemp(outputDir, "."+filename+".*.tmp")
	if err != nil {
		return fmt.Errorf("create temporary CSV for %s: %w", distribution, err)
	}
	temporaryPath := temporary.Name()
	committed := false
	defer func() {
		if !committed {
			_ = os.Remove(temporaryPath)
		}
	}()

	writer := csv.NewWriter(temporary)
	if err := writer.Write([]string{parameterHeader, "alpha_inflow", "distribution", "final_load", "avg_load", "load_std", "load_inflation", "converged", "full_block_fraction"}); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("write %s header: %w", filename, err)
	}
	for _, result := range results {
		summary := result.Summary
		record := []string{
			formatFloat(result.Point.Parameter),
			formatFloat(result.Point.Alpha),
			string(result.Point.Distribution),
			formatFloat(summary.FinalLoad),
			formatFloat(summary.AverageLoad),
			formatFloat(summary.LoadStd),
			formatFloat(summary.LoadInflation),
			formatBool(summary.Converged),
			formatFloat(summary.FullBlockFraction),
		}
		if err := writer.Write(record); err != nil {
			_ = temporary.Close()
			return fmt.Errorf("write %s row %d: %w", filename, result.Point.Index, err)
		}
	}
	writer.Flush()
	if err := writer.Error(); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("flush %s: %w", filename, err)
	}
	if err := temporary.Sync(); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("sync %s: %w", filename, err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("close %s: %w", filename, err)
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

// paperNames maps the paper's panel numbers onto the internal sweep ids, which
// predate the paper's final numbering. Only the paper's spellings are accepted,
// because the internal ids collide with different paper figures of the same
// number and a silent mismatch would be worse than an error.
var paperNames = map[string]Figure{
	"fig4a": Figure6,
	"fig4c": Figure7,
}

func ParseFigure(value string) (Figure, error) {
	figure, ok := paperNames[value]
	if !ok {
		return "", errors.New("figure must be fig4a or fig4c")
	}
	return figure, nil
}
