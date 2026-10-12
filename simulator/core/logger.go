package core

import (
	"fmt"
	"os"
	"sort"
	"strings"
	"time"
)

type SimulationLogger struct {
	simulation *Simulation
}

type SimulationStep struct {
	Step      int
	ShardData map[int]ShardStepData
}

type ShardStepData struct {
	TotalLoad           float64
	LoadRatio           float64
	Fee                 float64
	ProcessedLoads      []*Load
	PendingLoadAnalysis PendingLoadAnalysis
}

type PendingLoadAnalysis struct {
	TotalPending    float64
	LocalPending    float64
	OutboundPending float64
	InboundPending  float64
	EffectiveSteps  map[int]float64
}

func NewSimulationLogger(simulation *Simulation) *SimulationLogger {
	return &SimulationLogger{
		simulation: simulation,
	}
}

func (sl *SimulationLogger) RunAndLog() string {
	timestamp := time.Now().Format("20060102_150405")
	filename := fmt.Sprintf("enhanced_simulation_analysis_%s.log", timestamp)

	file, err := os.Create(filename)
	if err != nil {
		panic(fmt.Sprintf("Failed to create log file: %v", err))
	}
	defer file.Close()

	sl.writeLogHeader(file)

	var simulationData []SimulationStep

	sl.simulation.GenerateInitialLoad()

	shardIDs := make([]int, 0, len(sl.simulation.Shards))
	for shardID := range sl.simulation.Shards {
		shardIDs = append(shardIDs, shardID)
	}
	sort.Ints(shardIDs)

	for step := 0; step < sl.simulation.Config.Simulation.TotalSteps; step++ {
		stepData := SimulationStep{
			Step:      step,
			ShardData: make(map[int]ShardStepData),
		}

		for _, shardID := range shardIDs {
			shard := sl.simulation.Shards[shardID]
			demand := shard.GenerateDemand(step, &sl.simulation.Config)
			shard.PendingLoad = append(shard.PendingLoad, demand...)
		}

		for _, shardID := range shardIDs {
			shard := sl.simulation.Shards[shardID]
			pendingAnalysis := sl.analyzePendingLoad(shard, step)
			stepData.ShardData[shardID] = ShardStepData{
				PendingLoadAnalysis: pendingAnalysis,
			}
		}

		shardLoads := make(map[int]float64)
		processedLoads := make(map[int][]*Load)

		for _, shardID := range shardIDs {
			shardLoads[shardID] = 0.0
		}

		for _, shardID := range shardIDs {
			shard := sl.simulation.Shards[shardID]
			result := shard.AbstractLoad(step)
			processedLoads[shard.Spec.ID] = result

			for _, load := range result {
				if load.Forward {
					targetShard := sl.simulation.Shards[load.ShardTo]
					load.Forward = false
					load.EffectiveStep = step + load.DelayedStep
					targetShard.PendingLoad = append(targetShard.PendingLoad, load)
				}
				shardLoads[shard.Spec.ID] += load.Amount
			}
		}

		for _, shardID := range shardIDs {
			shard := sl.simulation.Shards[shardID]
			loadRatio := shardLoads[shardID] / shard.Spec.GMax
			shard.UpdateFee(loadRatio)
		}

		for _, shardID := range shardIDs {
			shard := sl.simulation.Shards[shardID]
			data := stepData.ShardData[shardID]
			data.TotalLoad = shardLoads[shardID]
			data.LoadRatio = shardLoads[shardID] / shard.Spec.GMax
			data.Fee = shard.Fee[len(shard.Fee)-1]
			data.ProcessedLoads = processedLoads[shardID]
			stepData.ShardData[shardID] = data
		}

		simulationData = append(simulationData, stepData)

		if step%50 == 0 {
			fmt.Printf("Processing step %d/%d\n", step, sl.simulation.Config.Simulation.TotalSteps)
		}
	}

	sl.writeDetailedAnalysis(file, simulationData)

	sl.writeDataSection(file, simulationData)

	return filename
}

func (sl *SimulationLogger) analyzePendingLoad(shard *Shard, currentStep int) PendingLoadAnalysis {
	analysis := PendingLoadAnalysis{
		EffectiveSteps: make(map[int]float64),
	}

	for _, load := range shard.PendingLoad {
		if load == nil {
			continue
		}

		if load.EffectiveStep <= currentStep {
			analysis.TotalPending += load.Amount
			analysis.EffectiveSteps[load.EffectiveStep] += load.Amount

			if load.ShardFrom == load.ShardTo {
				analysis.LocalPending += load.Amount
			} else if load.ShardFrom == shard.Spec.ID {
				analysis.OutboundPending += load.Amount
			} else {
				analysis.InboundPending += load.Amount
			}
		}
	}

	return analysis
}

func (sl *SimulationLogger) writeLogHeader(file *os.File) {
	config := sl.simulation.Config
	fmt.Fprintf(file, "╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗\n")
	fmt.Fprintf(file, "║                                                                              ENHANCED MULTI-SHARD GAS FEE SIMULATION ANALYSIS                                                                                        ║\n")
	fmt.Fprintf(file, "║                                                                                    Generated: %s                                                                                      ║\n", time.Now().Format("2006-01-02 15:04:05"))
	fmt.Fprintf(file, "╠══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣\n")
	fmt.Fprintf(file, "║ CONFIGURATION:                                                                                                                                                                                                              ║\n")
	fmt.Fprintf(file, "║ • Network: %d shards, each with capacity %s gas                                                                                                                                                                      ║\n",
		config.Network.NumShards, formatNumber(int(config.Shards[0].GMax)))
	fmt.Fprintf(file, "║ • Simulation Steps: %d                                                                                                                                                                                                     ║\n", config.Simulation.TotalSteps)
	fmt.Fprintf(file, "║ • Demand Shock: Steps %d-%d, %.1fx multiplier, targeting Shards %v                                                                                                                                                          ║\n",
		config.Simulation.DemandShock.StartStep, config.Simulation.DemandShock.EndStep, config.Simulation.DemandShock.Multiplier, config.Simulation.DemandShock.TargetShards)
	fmt.Fprintf(file, "║ • Enhanced Analysis: PendingLoad composition + EffectiveStep breakdown                                                                                                                                                     ║\n")
	fmt.Fprintf(file, "╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝\n\n")
}

func (sl *SimulationLogger) writeDetailedAnalysis(file *os.File, data []SimulationStep) {
	numShards := sl.simulation.Config.Network.NumShards

	fmt.Fprintf(file, "┌──────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐\n")
	fmt.Fprintf(file, "│ STEP │                                                                    ENHANCED SHARD ANALYSIS                                                                                                                            │\n")
	fmt.Fprintf(file, "├──────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤\n")
	fmt.Fprintf(file, "│      │")
	for i := 0; i < numShards; i++ {
		fmt.Fprintf(file, "                           SHARD %-2d                          │", i)
	}
	fmt.Fprintf(file, "\n│      │")
	for i := 0; i < numShards; i++ {
		fmt.Fprintf(file, " Fee/Load/Ratio │  Pending Analysis  │  Effective Steps   │")
	}
	fmt.Fprintf(file, "\n├──────┼")
	for i := 0; i < numShards; i++ {
		fmt.Fprintf(file, "────────────────┼────────────────────┼────────────────────┼")
	}
	fmt.Fprintf(file, "\n")

	for i, step := range data {
		if i%5 != 0 && i < len(data)-1 {
			continue
		}

		numShards := sl.simulation.Config.Network.NumShards
		fmt.Fprintf(file, "│ %4d │", step.Step)

		for shardID := 0; shardID < numShards; shardID++ {
			shardData := step.ShardData[shardID]

			fmt.Fprintf(file, " %5.3f/%5.0fk/%4.1f%% │",
				shardData.Fee,
				shardData.TotalLoad/1000,
				shardData.LoadRatio*100)

			fmt.Fprintf(file, " L:%3.0fk O:%3.0fk I:%3.0fk │",
				shardData.PendingLoadAnalysis.LocalPending/1000,
				shardData.PendingLoadAnalysis.OutboundPending/1000,
				shardData.PendingLoadAnalysis.InboundPending/1000)

			fmt.Fprintf(file, " %s │", sl.formatEffectiveSteps(shardData.PendingLoadAnalysis.EffectiveSteps, step.Step))
		}

		fmt.Fprintf(file, "\n")

		if step.Step >= sl.simulation.Config.Simulation.DemandShock.StartStep && step.Step <= sl.simulation.Config.Simulation.DemandShock.EndStep {
			fmt.Fprintf(file, "│      │              ⚡ DEMAND SHOCK PERIOD ⚡                                                                                                                                                          │\n")
		}
	}

	fmt.Fprintf(file, "└──────┴")
	for i := 0; i < numShards; i++ {
		fmt.Fprintf(file, "────────────────┴────────────────────┴────────────────────┴")
	}
	fmt.Fprintf(file, "\n\n")

	sl.writeSummaryAnalysis(file, data)
}

func (sl *SimulationLogger) formatEffectiveSteps(steps map[int]float64, currentStep int) string {
	if len(steps) == 0 {
		return "                  "
	}

	type stepLoad struct {
		step int
		load float64
	}

	var stepLoads []stepLoad
	for step, load := range steps {
		if load > 1000 {
			stepLoads = append(stepLoads, stepLoad{step, load})
		}
	}

	if len(stepLoads) == 0 {
		return "                  "
	}

	for i := 0; i < len(stepLoads)-1; i++ {
		for j := i + 1; j < len(stepLoads); j++ {
			if stepLoads[i].load < stepLoads[j].load {
				stepLoads[i], stepLoads[j] = stepLoads[j], stepLoads[i]
			}
		}
	}

	result := ""
	for i := 0; i < len(stepLoads) && i < 2; i++ {
		if i > 0 {
			result += " "
		}
		result += fmt.Sprintf("%d:%3.0fk", stepLoads[i].step, stepLoads[i].load/1000)
	}

	for len(result) < 18 {
		result += " "
	}

	return result
}

func (sl *SimulationLogger) writeSummaryAnalysis(file *os.File, data []SimulationStep) {
	numShards := sl.simulation.Config.Network.NumShards

	fmt.Fprintf(file, "╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗\n")
	fmt.Fprintf(file, "║                                                                                     CONVERGENCE ANALYSIS                                                                                                                       ║\n")
	fmt.Fprintf(file, "╠══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣\n")

	for shardID := 0; shardID < numShards; shardID++ {
		fmt.Fprintf(file, "║ SHARD %d CONVERGENCE:                                                                                                                                                                                                      ║\n", shardID)

		finalSteps := 50
		if len(data) < finalSteps {
			finalSteps = len(data)
		}

		avgFee := 0.0
		avgLoad := 0.0

		for i := len(data) - finalSteps; i < len(data); i++ {
			shardData := data[i].ShardData[shardID]
			avgFee += shardData.Fee
			avgLoad += shardData.LoadRatio
		}

		avgFee /= float64(finalSteps)
		avgLoad /= float64(finalSteps)

		fmt.Fprintf(file, "║   Final %d steps average: Fee = %.6f (target: 1.000000), Load Ratio = %.6f (target: 0.500000)                                                                                                               ║\n",
			finalSteps, avgFee, avgLoad)

		feeDeviation := ((avgFee - 1.0) / 1.0) * 100
		loadDeviation := ((avgLoad - 0.5) / 0.5) * 100

		fmt.Fprintf(file, "║   Deviation from targets: Fee %+.2f%%, Load %+.2f%%                                                                                                                                                                      ║\n",
			feeDeviation, loadDeviation)
	}

	fmt.Fprintf(file, "╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝\n\n")
}

func (sl *SimulationLogger) writeDataSection(file *os.File, data []SimulationStep) {
	numShards := sl.simulation.Config.Network.NumShards

	fmt.Fprintf(file, "# SIMULATION DATA FOR PYTHON VISUALIZATION\n")
	fmt.Fprintf(file, "# Format: Step")
	for i := 0; i < numShards; i++ {
		fmt.Fprintf(file, ",Shard%d_Fee", i)
	}
	for i := 0; i < numShards; i++ {
		fmt.Fprintf(file, ",Shard%d_Load", i)
	}
	fmt.Fprintf(file, "\n")
	fmt.Fprintf(file, "DATA_START\n")
	fmt.Fprintf(file, "Step")
	for i := 0; i < numShards; i++ {
		fmt.Fprintf(file, ",Shard%d_Fee", i)
	}
	for i := 0; i < numShards; i++ {
		fmt.Fprintf(file, ",Shard%d_Load", i)
	}
	fmt.Fprintf(file, "\n")

	for _, step := range data {
		fmt.Fprintf(file, "%d", step.Step)
		for i := 0; i < numShards; i++ {
			shardData := step.ShardData[i]
			fmt.Fprintf(file, ",%.17g", shardData.Fee)
		}
		for i := 0; i < numShards; i++ {
			shardData := step.ShardData[i]
			fmt.Fprintf(file, ",%.17g", shardData.LoadRatio)
		}
		fmt.Fprintf(file, "\n")
	}
	fmt.Fprintf(file, "DATA_END\n")
}

func formatNumber(n int) string {
	str := fmt.Sprintf("%d", n)
	if len(str) <= 3 {
		return str
	}

	var result []string
	for i, c := range str {
		if i > 0 && (len(str)-i)%3 == 0 {
			result = append(result, ",")
		}
		result = append(result, string(c))
	}

	return strings.Join(result, "")
}
