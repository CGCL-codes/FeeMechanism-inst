package nonuniform

import (
	"context"
	"encoding/csv"
	"fmt"
	"math/rand"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"sync"

	"gas-for-multiple-shards/core"
)

const (
	TargetLoad        = 0.5
	RelativeTolerance = 1e-3
	AbsoluteTolerance = TargetLoad * RelativeTolerance
	ConvergenceWindow = 50
	// TotalSteps is the simulated horizon. The first core.StatWarmup blocks
	// precede the demand shock and are excluded from the load statistics, so
	// this leaves 50,000 post-shock blocks.
	TotalSteps = 50100
	// MempoolCap is each chain's transaction-pool bound, in multiples of the
	// block gas limit. The value of 20 follows the default pool sizes of geth,
	// CometBFT, and Substrate. Zero restores an unbounded pool.
	MempoolCap = 20.0
	ShockStep  = 100
	InboundRatio      = 0.9
	InboundElasticity = 16.0
	BaseElasticity    = 1.5
	GridStep          = 0.001
	GridCount         = 150
	RandomSampleCount = 10000
	RandomSampleSeed  = 20260806
	NumShards         = 3
	shardGMax         = 2_000_000.0
	equilibriumLoad   = 1_000_000.0
)

type PerturbMode string

const (
	PerturbDistinct PerturbMode = "distinct"

	PerturbChainZero PerturbMode = "chain0"

	PerturbUniform PerturbMode = "uniform"

	PerturbChainOne PerturbMode = "chain1"
)

type Topology string

const (
	TopologyOutbound20 Topology = "outbound20"

	TopologyLocal20 Topology = "local20"

	TopologyLambda16 Topology = "lambda16"
)

type Point struct {
	Index    int
	Deltas   [NumShards]float64
	Perturb  PerturbMode
	Topology Topology
}

type ChainSummary struct {
	AverageLoad   float64
	LoadStd       float64
	LoadInflation float64
	Converged     bool

	// FullBlockFraction is the share of measured blocks that reach the gas
	// limit. It is the quantity every figure reports, because the bounded
	// transaction pool caps how far the realized load inflation can run.
	FullBlockFraction float64
}

type Result struct {
	Point        Point
	ConvergedAll bool
	Chains       [NumShards]ChainSummary

	MaxFeeDeviation0 float64
}

func GridPoints(mode PerturbMode) []Point {
	return GridPointsCount(mode, GridCount)
}

func GridPointsCount(mode PerturbMode, count int) []Point {
	return GridPointsTopology(mode, count, TopologyOutbound20)
}

func GridPointsTopology(mode PerturbMode, count int, topology Topology) []Point {
	points := make([]Point, 0, count*count)
	for i := 1; i <= count; i++ {
		delta0 := float64(i) * GridStep
		for j := 1; j <= count; j++ {
			deltaPeer := float64(j) * GridStep
			points = append(points, Point{
				Index:    len(points),
				Deltas:   [NumShards]float64{delta0, deltaPeer, deltaPeer},
				Perturb:  mode,
				Topology: topology,
			})
		}
	}
	return points
}

func Grid3DPoints(mode PerturbMode) []Point {
	const count = 63
	values := make([]float64, count)
	for k := range values {
		values[k] = 0.001 + 0.002*float64(k)
	}
	points := make([]Point, 0, count*count*count)
	for _, delta0 := range values {
		for _, delta1 := range values {
			for _, delta2 := range values {
				points = append(points, Point{
					Index:   len(points),
					Deltas:  [NumShards]float64{delta0, delta1, delta2},
					Perturb: mode,
				})
			}
		}
	}
	return points
}

func RandomPoints(mode PerturbMode) []Point {
	return RandomPointsCount(mode, GridCount)
}

func RandomPointsCount(mode PerturbMode, count int) []Point {
	generator := rand.New(rand.NewSource(RandomSampleSeed))
	maxDelta := float64(count) * GridStep
	points := make([]Point, 0, RandomSampleCount)
	for i := 0; i < RandomSampleCount; i++ {
		var deltas [NumShards]float64
		for k := range deltas {
			deltas[k] = GridStep + generator.Float64()*(maxDelta-GridStep)
		}
		points = append(points, Point{Index: i, Deltas: deltas, Perturb: mode})
	}
	return points
}

func ConfigFor(point Point) core.Config {
	toZeroPerPeer := equilibriumLoad * 0.40
	fromZeroPerPeer := equilibriumLoad * 0.10
	betweenPeers := equilibriumLoad * 0.25
	chainZeroLocal := equilibriumLoad * 0.20
	peerLocal := equilibriumLoad * 0.10

	demand := [][]float64{
		{0, fromZeroPerPeer, fromZeroPerPeer},
		{toZeroPerPeer, 0, betweenPeers},
		{toZeroPerPeer, betweenPeers, 0},
	}
	inboundSourceElasticity := BaseElasticity
	switch point.Topology {
	case TopologyLocal20:
		demand = [][]float64{
			{chainZeroLocal, 0, 0},
			{toZeroPerPeer, peerLocal, betweenPeers},
			{toZeroPerPeer, betweenPeers, peerLocal},
		}
	case TopologyLambda16:
		demand = [][]float64{
			{chainZeroLocal, 0, 0},
			{toZeroPerPeer, peerLocal, betweenPeers},
			{toZeroPerPeer, betweenPeers, peerLocal},
		}
		inboundSourceElasticity = InboundElasticity
	}
	lambda := [][]float64{
		{BaseElasticity, BaseElasticity, BaseElasticity},
		{inboundSourceElasticity, BaseElasticity, BaseElasticity},
		{inboundSourceElasticity, BaseElasticity, BaseElasticity},
	}

	shock := core.DemandShockConfig{
		Enabled:   true,
		StartStep: ShockStep,
		EndStep:   ShockStep + 1,
	}
	switch point.Perturb {
	case PerturbChainZero:
		shock.Multiplier = 1.01
		shock.TargetShards = []int{0}
	case PerturbUniform:
		shock.Multiplier = 1.01
		shock.TargetShards = []int{0, 1, 2}
	case PerturbChainOne:
		shock.Multiplier = 1.01
		shock.TargetShards = []int{1}
	default:
		shock.MultiplierPerShard = []float64{1.010, 1.011, 1.012}
		shock.TargetShards = []int{0, 1, 2}
	}

	return core.Config{
		Simulation: core.SimulationConfig{
			TotalSteps:    TotalSteps,
			LTarget:       TargetLoad,
			Delta:         point.Deltas[0],
			MempoolCap:    MempoolCap,
			DeltaPerShard: []float64{point.Deltas[0], point.Deltas[1], point.Deltas[2]},
			Perturbation:  core.PerturbationConfig{Enabled: false},
			DemandShock:   shock,
		},
		Network: core.NetworkConfig{NumShards: NumShards},
		Shards: []core.ShardSpec{
			{ID: 0, GMax: shardGMax},
			{ID: 1, GMax: shardGMax},
			{ID: 2, GMax: shardGMax},
		},
		Demand: core.DemandConfig{
			BaseDemandMatrix: demand,
			LambdaMatrix:     lambda,
			EpsilonMatrix: [][]float64{
				{0, InboundElasticity, InboundElasticity},
				{InboundElasticity, 0, InboundElasticity},
				{InboundElasticity, InboundElasticity, 0},
			},
		},
		Delay: core.DelayConfig{MaxDelay: 5, Weights: []float64{0, 0, 0, 0, 1}},
	}
}

func evaluatePoint(point Point) (Result, error) {
	config := ConfigFor(point)
	allLoads, err := core.RunAllLoadsFast(config)
	if err != nil {
		return Result{}, err
	}
	result := Result{Point: point, ConvergedAll: true}
	for shardID := 0; shardID < NumShards; shardID++ {
		summary := core.SummarizeObservedLoadWindow(
			core.TrimWarmup(allLoads[shardID], core.StatWarmup),
			TargetLoad, AbsoluteTolerance, ConvergenceWindow)
		result.Chains[shardID] = ChainSummary{
			AverageLoad:       summary.AverageLoad,
			LoadStd:           summary.LoadStd,
			LoadInflation:     summary.LoadInflation,
			Converged:         summary.Converged,
			FullBlockFraction: summary.FullBlockFraction,
		}
		if !summary.Converged {
			result.ConvergedAll = false
		}
	}
	result.MaxFeeDeviation0 = maxFeeDeviation(allLoads[0], point.Deltas[0])
	return result, nil
}

func maxFeeDeviation(loads []float64, delta float64) float64 {
	fee := 1.0
	maxDeviation := 0.0
	for _, load := range loads {
		fee *= 1 + delta*2*(load-TargetLoad)
		deviation := fee - 1
		if deviation < 0 {
			deviation = -deviation
		}
		if deviation > maxDeviation {
			maxDeviation = deviation
		}
	}
	return maxDeviation
}

type Options struct {
	Workers  int
	Progress func(done, total int)
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
				result, err := evaluatePoint(point)
				if err != nil {
					outcomes <- outcome{err: fmt.Errorf("point %d deltas=%v: %w", point.Index, point.Deltas, err)}
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
	for item := range outcomes {
		done++
		if options.Progress != nil {
			options.Progress(done, len(points))
		}
		if item.err != nil {
			if firstError == nil {
				firstError = item.err
			}
			continue
		}
		results = append(results, item.result)
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

func WriteCSV(outputDir, filename string, results []Result) error {
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return fmt.Errorf("create output directory: %w", err)
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
	header := []string{
		"delta0", "delta1", "delta2", "perturb", "converged_all",
		"converged0", "converged1", "converged2",
		"avg_load0", "avg_load1", "avg_load2",
		"inflation0", "inflation1", "inflation2",
		"load_std0", "load_std1", "load_std2",
		"full_block0", "full_block1", "full_block2",
		"max_fee_dev0",
	}
	if err := writer.Write(header); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("write header: %w", err)
	}
	for _, result := range results {
		record := []string{
			formatFloat(result.Point.Deltas[0]),
			formatFloat(result.Point.Deltas[1]),
			formatFloat(result.Point.Deltas[2]),
			string(result.Point.Perturb),
			formatBool(result.ConvergedAll),
			formatBool(result.Chains[0].Converged),
			formatBool(result.Chains[1].Converged),
			formatBool(result.Chains[2].Converged),
			formatFloat(result.Chains[0].AverageLoad),
			formatFloat(result.Chains[1].AverageLoad),
			formatFloat(result.Chains[2].AverageLoad),
			formatFloat(result.Chains[0].LoadInflation),
			formatFloat(result.Chains[1].LoadInflation),
			formatFloat(result.Chains[2].LoadInflation),
			formatFloat(result.Chains[0].LoadStd),
			formatFloat(result.Chains[1].LoadStd),
			formatFloat(result.Chains[2].LoadStd),
			formatFloat(result.Chains[0].FullBlockFraction),
			formatFloat(result.Chains[1].FullBlockFraction),
			formatFloat(result.Chains[2].FullBlockFraction),
			formatFloat(result.MaxFeeDeviation0),
		}
		if err := writer.Write(record); err != nil {
			_ = temporary.Close()
			return fmt.Errorf("write row: %w", err)
		}
	}
	writer.Flush()
	if err := writer.Error(); err != nil {
		_ = temporary.Close()
		return fmt.Errorf("flush: %w", err)
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
