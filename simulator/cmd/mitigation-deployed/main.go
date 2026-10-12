// Command mitigation-deployed reruns the two deployed Cosmos configurations of
// Table 2 under the compensated controller of Appendix D, and locates the
// stable interval of the estimation ratio gamma = H_i / Lambda_i^delay at each
// chain's deployed update rate. The intervals are the ones reported in Table 3.
package main

import (
	"encoding/csv"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strconv"

	"gas-for-multiple-shards/core"
)

type chainSpec struct {
	Name     string
	Alpha    float64
	DMax     int
	Deployed float64
}

// The measured inbound ratios and worst-case delays of Table 2, with each
// chain's deployed update rate.
var chains = []chainSpec{
	{Name: "cosmoshub", Alpha: 0.216, DMax: 10, Deployed: 0.125},
	{Name: "osmosis", Alpha: 0.248, DMax: 25, Deployed: 0.1},
}

const (
	gammaSteps = 300 // gamma walks 0.00 to 3.00 at step 0.01
	gammaUnit  = 100.0
)

// configFor mirrors cmd/deployed-chain: the inbound-coupled surrogate with the
// chain's measured inbound ratio, spike latency at its measured d_max, and the
// inbound elasticity fixed at 16.
func configFor(alpha, delta float64, dmax int) core.Config {
	target := 1_000_000.0
	in0 := target * alpha
	diag := target - in0
	cross := in0 / 4
	weights := make([]float64, dmax)
	weights[dmax-1] = 1
	return core.Config{
		Simulation: core.SimulationConfig{
			TotalSteps: 50100, LTarget: 0.5, Delta: delta,
			MempoolCap:   20,
			Perturbation: core.PerturbationConfig{Enabled: false},
			DemandShock: core.DemandShockConfig{
				Enabled: true, StartStep: 100, EndStep: 101,
				Multiplier: 1.01, TargetShards: []int{0},
			},
		},
		Network: core.NetworkConfig{NumShards: 3},
		Shards: []core.ShardSpec{
			{ID: 0, GMax: 2_000_000}, {ID: 1, GMax: 2_000_000}, {ID: 2, GMax: 2_000_000},
		},
		Demand: core.DemandConfig{
			BaseDemandMatrix: [][]float64{
				{diag, 0, 0}, {in0 / 2, diag, cross}, {in0 / 2, cross, diag},
			},
			LambdaMatrix:  [][]float64{{1.5, 1.5, 1.5}, {1.5, 1.5, 1.5}, {1.5, 1.5, 1.5}},
			EpsilonMatrix: [][]float64{{0, 1.5, 1.5}, {16, 0, 1.5}, {16, 1.5, 0}},
		},
		Delay: core.DelayConfig{MaxDelay: dmax, Weights: weights},
	}
}

func formatFloat(value float64) string {
	return strconv.FormatFloat(value, 'g', -1, 64)
}

func main() {
	outputDir := flag.String("output-dir", ".", "directory for the result CSV")
	flag.Parse()
	if err := os.MkdirAll(*outputDir, 0o755); err != nil {
		log.Fatal(err)
	}

	records := [][]string{{"chain", "alpha_inflow", "d_max", "delta", "gamma",
		"compensation_h0", "distribution", "final_load", "avg_load", "load_std",
		"load_inflation", "converged"}}
	for _, chain := range chains {
		base := configFor(chain.Alpha, chain.Deployed, chain.DMax)
		exact := core.ExactCompensationPerShard(&base)
		stable := make([]bool, gammaSteps+1)
		for i := 0; i <= gammaSteps; i++ {
			gamma := float64(i) / gammaUnit
			config := configFor(chain.Alpha, chain.Deployed, chain.DMax)
			gains := make([]float64, len(exact))
			for shard := range exact {
				gains[shard] = exact[shard] * gamma
			}
			config.Simulation.CompensationPerShard = gains
			summary, err := core.RunObservedLoadSummaryFastWindow(config, 0, 0.5, 0.0005, 50, core.StatWarmup)
			if err != nil {
				log.Fatal(err)
			}
			stable[i] = summary.Converged
			records = append(records, []string{
				chain.Name,
				formatFloat(chain.Alpha),
				strconv.Itoa(chain.DMax),
				formatFloat(chain.Deployed),
				formatFloat(gamma),
				formatFloat(gains[0]),
				"Spike",
				formatFloat(summary.FinalLoad),
				formatFloat(summary.AverageLoad),
				formatFloat(summary.LoadStd),
				formatFloat(summary.LoadInflation),
				strconv.FormatBool(summary.Converged),
			})
		}

		lower, upper, holes := -1, -1, 0
		for i, ok := range stable {
			if ok {
				if lower < 0 {
					lower = i
				}
				upper = i
			}
		}
		if lower >= 0 {
			for i := lower; i <= upper; i++ {
				if !stable[i] {
					holes++
				}
			}
		}
		fmt.Printf("%s: alpha=%.3f d_max=%d deployed delta=%.3f Lambda_delay=%.3f "+
			"stable gamma in [%.2f, %.2f] (holes: %d)\n",
			chain.Name, chain.Alpha, chain.DMax, chain.Deployed, exact[0],
			float64(lower)/gammaUnit, float64(upper)/gammaUnit, holes)
	}

	path := filepath.Join(*outputDir, "mitigation_deployed_Spike.csv")
	file, err := os.Create(path)
	if err != nil {
		log.Fatal(err)
	}
	writer := csv.NewWriter(file)
	if err := writer.WriteAll(records); err != nil {
		log.Fatal(err)
	}
	if err := file.Close(); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("wrote %d deterministic rows to %s\n", len(records)-1, path)
}
