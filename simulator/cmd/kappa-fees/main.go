// Command kappa-fees emits the base-fee trajectory of every chain for one point
// of the Figure 7 or Figure 8 sweep.
//
// Figures 7 and 8 originally drove the single-trajectory logger, which predates
// the bounded transaction pool and the 50,100-block horizon. This command runs
// the same configuration through the fast path instead, so it honours both, and
// writes the fees rather than a verdict. The base fee is an exact function of
// the realized load,
//
//	P_i(t) = P_i(t-1) * (1 + delta * 2 * (L_i(t) - 1/2)),
//
// starting from P_i(-1) = 1, and P_i(t) is the fee after block t, which is what
// the logger recorded. The kappa statistics stay in Python, where they were
// defined.
//
// The output is raw little-endian float64: chain 0's whole series, then chain
// 1's, then chain 2's.
package main

import (
	"bufio"
	"encoding/binary"
	"flag"
	"fmt"
	"math"
	"os"

	"gas-for-multiple-shards/core"
)

const (
	gasLimit   = 2_000_000.0
	targetLoad = 0.5
	baseElast  = 1.5
	numShards  = 3
)

// selfConsistentDemand is build_self_consistent_matrix of the kappa scripts:
// Chain 0 keeps (1-alpha) of the target load and receives alpha, split evenly
// between the peers. Each peer keeps the same local share and sends a quarter
// of alpha to the other peer.
func selfConsistentDemand(target, alpha float64) [][]float64 {
	if alpha < 0 {
		alpha = 0
	}
	if alpha > 1 {
		alpha = 1
	}
	local := (1 - alpha) * target
	toZero := 0.5 * alpha * target
	betweenPeers := 0.25 * alpha * target
	return [][]float64{
		{local, 0, 0},
		{toZero, local, betweenPeers},
		{toZero, betweenPeers, local},
	}
}

func square(value float64) [][]float64 {
	matrix := make([][]float64, numShards)
	for row := range matrix {
		matrix[row] = make([]float64, numShards)
		for column := range matrix[row] {
			matrix[row][column] = value
		}
	}
	return matrix
}

func delayWeights(distribution string) ([]float64, error) {
	switch distribution {
	case "Spike":
		return []float64{0, 0, 0, 0, 1}, nil
	case "Uniform":
		return []float64{0.2, 0.2, 0.2, 0.2, 0.2}, nil
	case "Bimodal":
		return []float64{0.4, 0, 0.2, 0, 0.4}, nil
	default:
		return nil, fmt.Errorf("unknown delay distribution %q", distribution)
	}
}

func main() {
	mode := flag.String("mode", "defense", "defense raises epsilon_j0, attack raises lambda_j0")
	distribution := flag.String("dist", "Spike", "Spike, Uniform, or Bimodal")
	parameter := flag.Float64("param", 0, "the swept elasticity, 0 to 16")
	alpha := flag.Float64("alpha", 0.01, "inbound ratio of Chain 0")
	delta := flag.Float64("delta", 0.125, "update rate, uniform across chains")
	totalSteps := flag.Int("total-steps", 50100, "simulated horizon in blocks")
	mempool := flag.Float64("mempool", 20, "transaction pool bound, in block gas limits")
	flag.Parse()

	weights, err := delayWeights(*distribution)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	lambda := square(baseElast)
	epsilon := square(baseElast)
	for shard := 0; shard < numShards; shard++ {
		epsilon[shard][shard] = 0
	}
	switch *mode {
	case "defense":
		epsilon[1][0] = *parameter
		epsilon[2][0] = *parameter
	case "attack":
		lambda[1][0] = *parameter
		lambda[2][0] = *parameter
	default:
		fmt.Fprintf(os.Stderr, "unknown mode %q\n", *mode)
		os.Exit(1)
	}

	config := core.Config{
		Simulation: core.SimulationConfig{
			TotalSteps:   *totalSteps,
			LTarget:      targetLoad,
			Delta:        *delta,
			MempoolCap:   *mempool,
			Perturbation: core.PerturbationConfig{Enabled: false},
			DemandShock: core.DemandShockConfig{
				Enabled: true, StartStep: 100, EndStep: 101,
				Multiplier: 1.01, TargetShards: []int{0},
			},
		},
		Network: core.NetworkConfig{NumShards: numShards},
		Shards: []core.ShardSpec{
			{ID: 0, GMax: gasLimit}, {ID: 1, GMax: gasLimit}, {ID: 2, GMax: gasLimit},
		},
		Demand: core.DemandConfig{
			BaseDemandMatrix: selfConsistentDemand(gasLimit*targetLoad, *alpha),
			LambdaMatrix:     lambda,
			EpsilonMatrix:    epsilon,
		},
		Delay: core.DelayConfig{MaxDelay: len(weights), Weights: weights},
	}

	loads, err := core.RunAllLoadsFast(config)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	writer := bufio.NewWriter(os.Stdout)
	buffer := make([]byte, 8)
	for shard := 0; shard < numShards; shard++ {
		fee := 1.0
		for _, load := range loads[shard] {
			fee *= 1 + *delta*2*(load-targetLoad)
			binary.LittleEndian.PutUint64(buffer, math.Float64bits(fee))
			if _, err := writer.Write(buffer); err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(1)
			}
		}
	}
	if err := writer.Flush(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
