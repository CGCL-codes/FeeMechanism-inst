package core

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Simulation SimulationConfig `yaml:"simulation"`
	Network    NetworkConfig    `yaml:"network"`
	Shards     []ShardSpec      `yaml:"shards"`
	Demand     DemandConfig     `yaml:"demand"`
	Delay      DelayConfig      `yaml:"delay"`
}

type SimulationConfig struct {
	TotalSteps int     `yaml:"total_steps"`
	LTarget    float64 `yaml:"l_target"`
	Delta      float64 `yaml:"delta"`

	DeltaPerShard []float64          `yaml:"delta_per_shard"`
	Perturbation  PerturbationConfig `yaml:"perturbation"`
	DemandShock   DemandShockConfig  `yaml:"demand_shock"`

	// Compensation is the gain H_i of the phase-lead term that cancels the
	// delayed self-feedback of Channel (III). Zero reproduces plain EIP-1559.
	Compensation         float64   `yaml:"compensation"`
	CompensationPerShard []float64 `yaml:"compensation_per_shard"`

	// MempoolCap bounds each chain's pool of eligible-but-unincluded gas at
	// MempoolCap times that chain's block gas limit. A full pool refuses
	// arriving gas, which is what a production transaction pool does. Zero
	// disables the bound and reproduces an unbounded pool.
	MempoolCap float64 `yaml:"mempool_cap"`
}

type PerturbationConfig struct {
	Enabled   bool    `yaml:"enabled"`
	Amplitude float64 `yaml:"amplitude"`
	Period    int     `yaml:"period"`
}

type DemandShockConfig struct {
	Enabled    bool    `yaml:"enabled"`
	StartStep  int     `yaml:"start_step"`
	EndStep    int     `yaml:"end_step"`
	Multiplier float64 `yaml:"multiplier"`

	MultiplierPerShard []float64 `yaml:"multiplier_per_shard"`
	TargetShards       []int     `yaml:"target_shards"`
}

type NetworkConfig struct {
	NumShards int `yaml:"num_shards"`
}

type ShardSpec struct {
	ID   int     `yaml:"id"`
	GMax float64 `yaml:"g_max"`
}

type DemandConfig struct {
	BaseDemandMatrix [][]float64 `yaml:"base_demand_matrix"`
	LambdaMatrix     [][]float64 `yaml:"lambda_matrix"`
	EpsilonMatrix    [][]float64 `yaml:"epsilon_matrix"`

	// InboundElasticityRamp overrides the constant epsilon_{j->Chain} entries of
	// EpsilonMatrix with a value that rises linearly in the realized load of the
	// destination chain. Disabled by default, so a zero value reproduces the
	// constant-elasticity model of the paper exactly.
	InboundElasticityRamp ElasticityRamp `yaml:"inbound_elasticity_ramp"`
}

// ElasticityRamp is the load-dependent cross-chain elasticity of one destination
// chain. The elasticity is AtZeroLoad when the destination chain is empty and
// AtRefLoad when its realized load ratio reaches RefLoad, and it interpolates
// linearly in between. Clamp holds the elasticity at AtRefLoad above RefLoad.
type ElasticityRamp struct {
	Enabled     bool    `yaml:"enabled"`
	Chain       int     `yaml:"chain"`
	AtZeroLoad  float64 `yaml:"at_zero_load"`
	AtRefLoad   float64 `yaml:"at_ref_load"`
	RefLoad     float64 `yaml:"ref_load"`
	Clamp       bool    `yaml:"clamp"`
	InitialLoad float64 `yaml:"initial_load"`

	// Knots and Values give an arbitrary shape instead of the two-point ramp.
	// Both must be the same length and Knots must increase. The elasticity is
	// linear between neighbouring knots and constant outside the range.
	Knots  []float64 `yaml:"knots"`
	Values []float64 `yaml:"values"`

	// Driver selects the quantity the shape reads. "load" is the destination
	// chain's realized load ratio, the default. "price" is its base fee, which
	// is the natural driver when the elasticity is a property of the demand
	// curve rather than of congestion.
	Driver string `yaml:"driver"`
}

// At returns the elasticity that a source chain faces at the given driver
// value, which is the destination chain's load ratio unless Driver is "price".
func (ramp ElasticityRamp) At(driver float64) float64 {
	if len(ramp.Knots) >= 2 {
		return interpolate(ramp.Knots, ramp.Values, driver)
	}
	reference := ramp.RefLoad
	if reference <= 0 {
		reference = 1
	}
	fraction := driver / reference
	if fraction < 0 {
		fraction = 0
	}
	if ramp.Clamp && fraction > 1 {
		fraction = 1
	}
	return ramp.AtZeroLoad + (ramp.AtRefLoad-ramp.AtZeroLoad)*fraction
}

// UsesPrice reports whether the shape reads the destination base fee.
func (ramp ElasticityRamp) UsesPrice() bool {
	return ramp.Driver == "price"
}

func interpolate(knots, values []float64, x float64) float64 {
	if x <= knots[0] {
		return values[0]
	}
	last := len(knots) - 1
	if x >= knots[last] {
		return values[last]
	}
	for index := 0; index < last; index++ {
		if x <= knots[index+1] {
			span := knots[index+1] - knots[index]
			if span <= 0 {
				return values[index+1]
			}
			weight := (x - knots[index]) / span
			return values[index] + (values[index+1]-values[index])*weight
		}
	}
	return values[last]
}

type DelayConfig struct {
	MaxDelay int       `yaml:"max_delay"`
	Weights  []float64 `yaml:"weights"`
}

func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	var config Config
	err = yaml.Unmarshal(data, &config)
	if err != nil {
		return nil, fmt.Errorf("failed to unmarshal config YAML: %w", err)
	}

	if err := validateConfig(&config); err != nil {
		return nil, fmt.Errorf("config validation failed: %w", err)
	}

	return &config, nil
}

func validateConfig(c *Config) error {
	numShards := c.Network.NumShards
	if numShards <= 0 {
		return fmt.Errorf("num_shards must be positive")
	}

	if len(c.Shards) != numShards {
		return fmt.Errorf("number of items in shards list (%d) does not match num_shards (%d)", len(c.Shards), numShards)
	}

	if err := validateMatrix(c.Demand.BaseDemandMatrix, numShards, "base_demand_matrix"); err != nil {
		return err
	}
	if err := validateMatrix(c.Demand.LambdaMatrix, numShards, "lambda_matrix"); err != nil {
		return err
	}
	if err := validateMatrix(c.Demand.EpsilonMatrix, numShards, "epsilon_matrix"); err != nil {
		return err
	}

	if c.Delay.MaxDelay != len(c.Delay.Weights) {
		return fmt.Errorf("max_delay (%d) does not match the number of weights (%d)", c.Delay.MaxDelay, len(c.Delay.Weights))
	}

	return nil
}

func validateMatrix(matrix [][]float64, expectedDim int, name string) error {
	if len(matrix) != expectedDim {
		return fmt.Errorf("%s has %d rows, expected %d", name, len(matrix), expectedDim)
	}
	for i, row := range matrix {
		if len(row) != expectedDim {
			return fmt.Errorf("row %d of %s has %d columns, expected %d", i, name, len(row), expectedDim)
		}
	}
	return nil
}
