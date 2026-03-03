This framework:

* Fixes inconsistencies in the original emulator implementation

* Provides configurable sampling strategies

* Generates detailed logs and CSV traces

* Performs statistical analysis

* Supports historical comparison across test runs

* Produces visualization outputs

* Computes precision metrics (CV, CI95)

## Code fixing:

main.py:
Greenlee ammeter runs on port 5000 per usage file not 5001 => update update def run emulator 
Entes ammeter runs on port 5001 per usage file not 5002 => update update def run emulator
Circutor ammeter runs on port 5002 per usage file not 5003 => update update def run emulator 

Greenlee request_current_from_ammeter command not according to usage file => update request b"MEASURE_GREENLEE -get_measurement"
Entes request_current_from_ammeter command not according to usage file => update request b'MEASURE_ENTES -get_data'
Circutor request_current_from_ammeter command not according to usage file => update request b'MEASURE_CIRCUTOR -get_measurement'

reenlee request_current_from_ammeter port arg not according to usage file => update port 5000
Entes request_current_from_ammeter port arg not according to usage file => update 5001
Circutor request_current_from_ammeter port arg not according to usage file => update 5002

test_framework.py:
def run_test(self, ammeter_type: str) return type syntax wrong => fixed

client.py
request_current_from_ammeter():
return val is now float
return -1 when no data
added timeout to tcp send and exception for getting it

Circutor_Ammeter.py:
get_current_command() fix bug return command to MEASURE_CIRCUTOR -get_measurement


config.yaml:
I've added args :     expected_range:
      min: 
      max: 

which tells what is the expected range of outputs.
This args were calculated based on the specification and are sensitive to future code changes 


It is advisable and more robust to calculate the min, max
range of outputs dynamically from the specs. Unfortunately this is only possible with additions to the api:
for example if the ammeters classes supported the following api calls: self.get_current_command_min/max.
We could have computed the range dynamically. 
I've decided to not add the api calls and compute them to shorten the solution time.
In real life scenario I would have advised the devs to consider adding them.

## Running Tests

pytest -q -vv --config=config/config.yaml

Explanation:

-q → quiet output

-vv → verbose test details

--config → load specific YAML configuration

You can switch configuration files to produce different behaviors.
Check example configurations at config/

### Sampling Policy

Sampling plan is derived automatically:

If only measurements_count is set → sampling frequency defaults to sampling_frequency_min_val

If duration + count provided → frequency is derived

If duration + frequency provided → count derived

Validates constraints to avoid invalid configurations

### Output Structure

tests/out/<timestamp>/ <> tests/out/2026-03-01T15-20-11/

### run.log

* Complete execution log including:
* Configuration summary
* Sampling plan
* Per-measurement status
* Plot generation
Example in tests/out/any_dir/run.log

### CSV per Ammeter
Hold all relevant data for each Ammeter that we run
in a csv format for example if we sampled 200 times, we will have 200 rows each.
Example in tests/out/any_dir/circutor.csv

| Column       | Meaning                     |
| ------------ | --------------------------- |
| t_epoch_s    | epoch timestamp             |
| ammeter      | device name                 |
| value        | measured value              |
| status       | OK / OUT_OF_RANGE / NO_DATA |
| expected_min | expected lower bound        |
| expected_max | expected upper bound        |

### Analysis directory
Example in tests/out/any_dir/analysis/stats.json
Calculates per Ammeter:
{
  "mean": ...,
  "median": ...,
  "stdev": ...,
  "stdev_normalized": ...,
  "confidence_interval_95": ...,
  "count_ok": ...,
  "count_total": ...
}

### Visualization
if enabled : tests/out/any_dir/analysis/plots/
Will run .pngs per arg in configuration file

for example:
greenlee__simple_value_time.png
entes__simple_value_time.png
circutor__simple_value_time.png
![Greenlee Plot](https://raw.githubusercontent.com/CornPump/AmmetersPytest/main/tests/out/2026-03-01T16-56-01/analysis/plots/greenlee__simple_value_time.png)
## Historical Comparison CLI

python tests/compare_stats.py --runs-dir tests/out --ammeters greenlee entes circutor
Compare multiple runs
### Generates:
in out/statistic/<timestamp>/
cross run statistics

### Includes:
Per-ammeter plots for:
mean
median
stdev
stdev_normalized

Unified comparison plots (if multiple ammeters selected)
Plotting the Ammeters on the same plot.
![Unified STDEV Normalized](https://raw.githubusercontent.com/CornPump/AmmetersPytest/main/out/statistic/2026-03-01T18-29-00/unified__stdev_normalized.png)
summary.json

### Each plot:
X = run index
Y = metric value
Dot-based visualization

## Precision Analysis CLI

python tests/compare_stats.py --runs-dir tests/out --precision --per-run

### Computes:

Coefficient of Variation (CV)
95% Confidence Interval (CI95)
Across historical runs.

### Example output:

=== Precision report (cross-run) ===

[circutor]
  CV:   count=11 mean=0.497 median=0.498 min=0.345 max=0.656
  CI95: count=11 mean=0.00339 median=0.00150 min=0.00144 max=0.00773

[entes]
  CV:   count=11 mean=0.625 median=0.620 min=0.582 max=0.713
  CI95: count=11 mean=10.14 median=4.13 min=3.96 max=23.54

[greenlee]
  CV:   count=10 mean=3.69 median=3.69 min=1.36 max=5.49
  CI95: count=10 mean=0.345 median=0.191 min=0.071 max=1.52

### Interpretation 

CV → relative precision (noise level)

CI95 → uncertainty of mean estimate

Lower CV = more reliable measurement process

Lower CI95 = tighter mean estimation

#### Based on sample results for current code:

Circutor → most precise

Entes → moderate precision

Greenlee → high variability