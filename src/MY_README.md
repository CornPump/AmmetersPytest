Fixing the code itself:

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