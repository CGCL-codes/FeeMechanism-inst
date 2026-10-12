package appendix

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
	Figure10 Figure = "fig10"
	Figure11 Figure = "fig11"
	Figure12 Figure = "fig12"
	Figure13 Figure = "fig13"
	Figure14 Figure = "fig14"
)

type Distribution string

const (
	Spike   Distribution = "Spike"
	Uniform Distribution = "Uniform"
	Bimodal Distribution = "Bimodal"
)

const (
	targetLoad                   = 0.5
	relativeConvergenceTolerance = 1e-3
	absoluteConvergenceTolerance = targetLoad * relativeConvergenceTolerance
	convergenceWindow            = 50
	shockStart                   = 100
	shockEnd                     = 101
	shockMultiplier              = 1.01
	defaultElasticity            = 1.5
	gasLimit                     = 2_000_000.0
	targetDemand                 = gasLimit / 2.0
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
	MaxDelay     int
	NumShards    int
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

type scenario struct {
	distribution Distribution
	maxDelay     int
	numShards    int
}

func scenarios(figure Figure) []scenario {
	switch figure {
	case Figure10, Figure11:
		return []scenario{
			{distribution: Spike, maxDelay: 5, numShards: 3},
			{distribution: Uniform, maxDelay: 5, numShards: 3},
			{distribution: Bimodal, maxDelay: 5, numShards: 3},
		}
	case Figure12:
		return []scenario{{distribution: Spike, maxDelay: 1, numShards: 3}}
	case Figure13:
		return []scenario{
			{distribution: Uniform, maxDelay: 5, numShards: 3},
			{distribution: Spike, maxDelay: 5, numShards: 3},
			{distribution: Uniform, maxDelay: 7, numShards: 3},
			{distribution: Spike, maxDelay: 7, numShards: 3},
			{distribution: Uniform, maxDelay: 10, numShards: 3},
			{distribution: Spike, maxDelay: 10, numShards: 3},
		}
	case Figure14:
		return []scenario{
			{distribution: Spike, maxDelay: 5, numShards: 5},
			{distribution: Spike, maxDelay: 5, numShards: 7},
			{distribution: Spike, maxDelay: 5, numShards: 10},
		}
	default:
		return nil
	}
}

func Points(figure Figure) []Point {
	figureScenarios := scenarios(figure)
	if len(figureScenarios) == 0 {
		return nil
	}
	points := make([]Point, 0, len(figureScenarios)*161*99)
	for _, current := range figureScenarios {
		for parameterIndex := 160; parameterIndex >= 0; parameterIndex-- {
			for alphaIndex := 99; alphaIndex >= 1; alphaIndex-- {
				points = append(points, Point{
					Index:        len(points),
					Figure:       figure,
					Distribution: current.distribution,
					Parameter:    float64(parameterIndex) / 10.0,
					Alpha:        float64(alphaIndex) / 100.0,
					MaxDelay:     current.maxDelay,
					NumShards:    current.numShards,
				})
			}
		}
	}
	return points
}

func ConfigFor(point Point) (core.Config, error) {
	if point.Alpha < 0.01 || point.Alpha > 0.99 {
		return core.Config{}, fmt.Errorf("alpha %g is outside [0.01, 0.99]", point.Alpha)
	}
	if point.Parameter < 0 || point.Parameter > 16 {
		return core.Config{}, fmt.Errorf("parameter %g is outside [0, 16]", point.Parameter)
	}
	if point.NumShards < 3 {
		return core.Config{}, fmt.Errorf("num_shards %d is below 3", point.NumShards)
	}
	weights, err := delayWeights(point.Distribution, point.MaxDelay)
	if err != nil {
		return core.Config{}, err
	}

	shards := make([]core.ShardSpec, point.NumShards)
	for shardID := range shards {
		shards[shardID] = core.ShardSpec{ID: shardID, GMax: gasLimit}
	}
	lambda := squareMatrix(point.NumShards, defaultElasticity, false)
	epsilon := squareMatrix(point.NumShards, defaultElasticity, true)

	var demand [][]float64
	switch point.Figure {
	case Figure10:
		if point.NumShards != 3 || point.MaxDelay != 5 {
			return core.Config{}, fmt.Errorf("Figure 10 requires three chains and dmax=5")
		}
		for source := 1; source < point.NumShards; source++ {
			lambda[source][0] = point.Parameter
		}
		demand = inboundDemandMatrix(point.Alpha, point.NumShards)
	case Figure11:
		if point.NumShards != 3 || point.MaxDelay != 5 {
			return core.Config{}, fmt.Errorf("Figure 11 requires three chains and dmax=5")
		}
		epsilon[0][1] = point.Parameter
		epsilon[0][2] = point.Parameter
		demand = outboundDemandMatrix(point.Alpha)
	case Figure12:
		if point.NumShards != 3 || point.MaxDelay != 1 || point.Distribution != Spike {
			return core.Config{}, fmt.Errorf("Figure 12 requires three chains and spike dmax=1")
		}
		epsilon[0][1] = point.Parameter
		epsilon[0][2] = point.Parameter
		demand = outboundDemandMatrix(point.Alpha)
	case Figure13:
		if point.NumShards != 3 || (point.MaxDelay != 5 && point.MaxDelay != 7 && point.MaxDelay != 10) {
			return core.Config{}, fmt.Errorf("Figure 13 requires three chains and dmax=5, 7, or 10")
		}
		for source := 1; source < point.NumShards; source++ {
			epsilon[source][0] = point.Parameter
		}
		demand = inboundDemandMatrix(point.Alpha, point.NumShards)
	case Figure14:
		if (point.NumShards != 5 && point.NumShards != 7 && point.NumShards != 10) || point.MaxDelay != 5 || point.Distribution != Spike {
			return core.Config{}, fmt.Errorf("Figure 14 requires spike dmax=5 and 5, 7, or 10 chains")
		}
		for source := 1; source < point.NumShards; source++ {
			epsilon[source][0] = point.Parameter
		}
		demand = inboundDemandMatrix(point.Alpha, point.NumShards)
	default:
		return core.Config{}, fmt.Errorf("unknown figure %q", point.Figure)
	}

	return core.Config{
		Simulation: core.SimulationConfig{
			TotalSteps: TotalSteps,
			LTarget:    targetLoad,
			Delta:      0.125,
			MempoolCap: MempoolCap,
			Perturbation: core.PerturbationConfig{
				Enabled: false,
			},
			DemandShock: core.DemandShockConfig{
				Enabled:      true,
				StartStep:    shockStart,
				EndStep:      shockEnd,
				Multiplier:   shockMultiplier,
				TargetShards: []int{0},
			},
		},
		Network: core.NetworkConfig{NumShards: point.NumShards},
		Shards:  shards,
		Demand: core.DemandConfig{
			BaseDemandMatrix: demand,
			LambdaMatrix:     lambda,
			EpsilonMatrix:    epsilon,
		},
		Delay: core.DelayConfig{MaxDelay: point.MaxDelay, Weights: weights},
	}, nil
}

func squareMatrix(dimension int, value float64, zeroDiagonal bool) [][]float64 {
	matrix := make([][]float64, dimension)
	for row := 0; row < dimension; row++ {
		matrix[row] = make([]float64, dimension)
		for column := 0; column < dimension; column++ {
			matrix[row][column] = value
			if zeroDiagonal && row == column {
				matrix[row][column] = 0
			}
		}
	}
	return matrix
}

func inboundDemandMatrix(alpha float64, numShards int) [][]float64 {
	matrix := make([][]float64, numShards)
	for row := range matrix {
		matrix[row] = make([]float64, numShards)
		matrix[row][row] = (1 - alpha) * targetDemand
	}
	perSourceInbound := alpha * targetDemand / float64(numShards-1)
	betweenOtherChains := alpha * targetDemand / float64(2*(numShards-1))
	for source := 1; source < numShards; source++ {
		matrix[source][0] = perSourceInbound
		for destination := 1; destination < numShards; destination++ {
			if destination != source {
				matrix[source][destination] = betweenOtherChains
			}
		}
	}
	return matrix
}

func outboundDemandMatrix(alpha float64) [][]float64 {
	diagonal := (1 - alpha) * targetDemand
	return [][]float64{
		{diagonal, alpha * targetDemand / 2, alpha * targetDemand / 2},
		{0, diagonal, alpha * targetDemand / 4},
		{0, alpha * targetDemand / 4, diagonal},
	}
}

func delayWeights(distribution Distribution, maxDelay int) ([]float64, error) {
	switch {
	case distribution == Spike && maxDelay == 1:
		return []float64{1}, nil
	case distribution == Spike && maxDelay == 3:
		return []float64{0, 0, 1}, nil
	case distribution == Uniform && maxDelay == 3:
		return []float64{0.33, 0.33, 0.34}, nil
	case distribution == Spike && maxDelay == 5:
		return []float64{0, 0, 0, 0, 1}, nil
	case distribution == Uniform && maxDelay == 5:
		return []float64{0.2, 0.2, 0.2, 0.2, 0.2}, nil
	case distribution == Bimodal && maxDelay == 5:
		return []float64{0.4, 0, 0.2, 0, 0.4}, nil
	case distribution == Spike && maxDelay == 7:
		return []float64{0, 0, 0, 0, 0, 0, 1}, nil
	case distribution == Uniform && maxDelay == 7:
		return []float64{0.14, 0.14, 0.14, 0.14, 0.14, 0.15, 0.15}, nil
	case distribution == Spike && maxDelay == 10:
		return []float64{0, 0, 0, 0, 0, 0, 0, 0, 0, 1}, nil
	case distribution == Uniform && maxDelay == 10:
		return []float64{0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1}, nil
	default:
		return nil, fmt.Errorf("unsupported %s distribution with dmax=%d", distribution, maxDelay)
	}
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
		targetLoad,
		absoluteConvergenceTolerance,
		convergenceWindow,
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
					outcomes <- outcome{err: fmt.Errorf("%s %s dmax=%d N=%d parameter=%g alpha=%g: %w", point.Figure, point.Distribution, point.MaxDelay, point.NumShards, point.Parameter, point.Alpha, err)}
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
	sort.Slice(results, func(i, j int) bool { return results[i].Point.Index < results[j].Point.Index })
	return results, nil
}

func isContextError(err error) bool {
	return errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded)
}

type outputGroup struct {
	directory string
	filename  string
	results   []Result
}

func WriteCSVs(outputDir string, figure Figure, results []Result) error {
	if len(scenarios(figure)) == 0 {
		return fmt.Errorf("unknown figure %q", figure)
	}
	groups := make(map[string]*outputGroup)
	for _, result := range results {
		if result.Point.Figure != figure {
			return fmt.Errorf("result %d belongs to %s, not %s", result.Point.Index, result.Point.Figure, figure)
		}
		directory, filename := outputLocation(figure, result.Point)
		key := filepath.Join(directory, filename)
		group := groups[key]
		if group == nil {
			group = &outputGroup{directory: directory, filename: filename}
			groups[key] = group
		}
		group.results = append(group.results, result)
	}
	keys := make([]string, 0, len(groups))
	for key := range groups {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		group := groups[key]
		directory := filepath.Join(outputDir, group.directory)
		if err := os.MkdirAll(directory, 0o755); err != nil {
			return fmt.Errorf("create output directory: %w", err)
		}
		sort.Slice(group.results, func(i, j int) bool { return group.results[i].Point.Index < group.results[j].Point.Index })
		if err := writeCSV(filepath.Join(directory, group.filename), figure, group.results); err != nil {
			return err
		}
	}
	return nil
}

func outputLocation(figure Figure, point Point) (string, string) {
	switch figure {
	case Figure10, Figure11, Figure12:
		return "", fmt.Sprintf("attack_defense_results_%s.csv", point.Distribution)
	case Figure13:
		return fmt.Sprintf("dmax%d", point.MaxDelay), fmt.Sprintf("convergence_results_%s.csv", point.Distribution)
	case Figure14:
		return "", fmt.Sprintf("convergence_results_spike_shard%d.csv", point.NumShards)
	default:
		return "", ""
	}
}

func writeCSV(finalPath string, figure Figure, results []Result) error {
	directory := filepath.Dir(finalPath)
	temporary, err := os.CreateTemp(directory, "."+filepath.Base(finalPath)+".*.tmp")
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
	if err := writer.Write(csvHeader(figure)); err != nil {
		_ = temporary.Close()
		return err
	}
	for _, result := range results {
		if err := writer.Write(csvRecord(figure, result)); err != nil {
			_ = temporary.Close()
			return err
		}
	}
	writer.Flush()
	if err := writer.Error(); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	if err := os.Rename(temporaryPath, finalPath); err != nil {
		return err
	}
	committed = true
	return nil
}

func csvHeader(figure Figure) []string {
	base := []string{"distribution", "final_load", "avg_load", "load_std", "load_inflation", "converged", "full_block_fraction"}
	switch figure {
	case Figure10:
		return append([]string{"lambda_j0", "alpha_inflow"}, base...)
	case Figure11, Figure12:
		return append([]string{"epsilon_0j", "alpha_outflow"}, base...)
	case Figure13:
		return append([]string{"epsilon_j0", "alpha_inflow"}, base...)
	case Figure14:
		return append([]string{"num_shards", "epsilon_j0", "alpha_inflow"}, base...)
	default:
		return nil
	}
}

func csvRecord(figure Figure, result Result) []string {
	summary := result.Summary
	base := []string{
		string(result.Point.Distribution),
		formatFloat(summary.FinalLoad),
		formatFloat(summary.AverageLoad),
		formatFloat(summary.LoadStd),
		formatFloat(summary.LoadInflation),
		formatBool(summary.Converged),
		formatFloat(summary.FullBlockFraction),
	}
	switch figure {
	case Figure10, Figure11, Figure12, Figure13:
		return append([]string{formatFloat(result.Point.Parameter), formatFloat(result.Point.Alpha)}, base...)
	case Figure14:
		return append([]string{strconv.Itoa(result.Point.NumShards), formatFloat(result.Point.Parameter), formatFloat(result.Point.Alpha)}, base...)
	default:
		return nil
	}
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

// paperNames maps the paper's figure numbers onto the internal sweep ids, which
// predate the paper's final numbering. Only the paper's spellings are accepted,
// because several internal ids collide with a different paper figure of the same
// number and a silent mismatch would be worse than an error.
var paperNames = map[string]Figure{
	"fig9-top":    Figure10,
	"fig9-bottom": Figure11,
	"fig10":       Figure12,
	"fig12":       Figure13,
	"fig13":       Figure14,
}

func ParseFigure(value string) (Figure, error) {
	figure, ok := paperNames[value]
	if !ok {
		return "", errors.New("figure must be fig9-top, fig9-bottom, fig10, fig12, or fig13")
	}
	return figure, nil
}
