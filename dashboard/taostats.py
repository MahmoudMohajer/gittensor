# %%
import requests, json, time
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import decimal
from datetime import datetime, timedelta
from rich import print
from substrateinterface.utils.ss58 import ss58_encode
api_key=""

# %%
coldkeys = []


# %%
def convert_address(address):
    # Remove the "0x" prefix and convert the address from hex to bytes
    address_bytes = bytes.fromhex(address[2:])

    # Encode the address into SS58 format
    ss58_address = ss58_encode(address_bytes)

    return ss58_address

# %%
#sometimes the chain spits out a time with milliseconds.. Sometimess it doesnt.  Its annoying.
#this fixes it. returns a datetime object
def stupid_time_fix(timestamp):
    if len(timestamp) > 20:
        date_obj = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        date_obj = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    unix_timestamp = int(date_obj.timestamp())
    return unix_timestamp

# %%
##get all extrinsics for the coldkeya

all_extrinsics = []


for coldkey in coldkeys:
    #get all the extrinsics
    page=1
    count=200
    while count >0:
    
        url = f"https://api.taostats.io/api/extrinsic/v1?signer_address={coldkey}&page={page}&limit={count}" #&extrinsic_name={extrinsic_name}
        
        headers = {
            "accept": "application/json",
            "Authorization": api_key
        }
        
        response = requests.get(url, headers=headers)
        resJson = json.loads(response.text)
 
        all_extrinsics += resJson['data']
        if len(resJson['data']) <200:
            #we have hot the last round
            count = 0
        else:
            page +=1
    

# %%
extrinsic_count = {}

for extrinsic in all_extrinsics:
    name = extrinsic['full_name']
    if name in extrinsic_count:
        extrinsic_count[name] +=1
    else:
        extrinsic_count[name] =1
print(extrinsic_count)

# %%
#here are some of the extrinsics we can work with
#in this notebook, I am focusing on burned register - buying neurons

for extrinsic in all_extrinsics:
    name = extrinsic['full_name']
    if name == "Balances.transfer_allow_death":
        print(extrinsic)
        break
for extrinsic in all_extrinsics:
    name = extrinsic['full_name']
    if name == "SubtensorModule.burned_register":
        print(extrinsic)
        break
for extrinsic in all_extrinsics:
    name = extrinsic['full_name']
    if name == "SubtensorModule.remove_stake":
        print(extrinsic)
        break    
for extrinsic in all_extrinsics:
    name = extrinsic['full_name']
    if name == "Balances.transfer":
        print(extrinsic)
        break    
for extrinsic in all_extrinsics:
    name = extrinsic['full_name']
    if name == "SubtensorModule.add_stake":
        print(extrinsic)
        break    

# %%
neuron_registration_data = []
for extrinsic in all_extrinsics:
   
    #if a registration, get the end tmestamp
    #to be a registration there must be burned register, and successful extrisic
    if extrinsic['full_name'] =="SubtensorModule.burned_register" and extrinsic['success']:
        coldkey = extrinsic['signer_address']
        hotkey = convert_address(extrinsic['call_args']['hotkey'])
        extrinsic_id = extrinsic['id']
        start_block = extrinsic['block_number']
        netuid = extrinsic['call_args']['netuid'] 
        start_time = extrinsic['timestamp']
        end_block=0
        end_time=""
        emission = 0
        #get the deregistration block, timestamp
        #old version requres the hex hotkey
        #This will tell us how long the miner was registered
        url1=f"https://api.taostats.io/api/v1/subnet/neuron/deregistration?netuid={netuid}&hotkey={extrinsic['call_args']['hotkey']}&block_start={start_block}&limit=1&order=timestamp_asc"
        response1 = requests.get(url1, headers=headers)
        resJson1 = json.loads(response1.text)
        if resJson1['pagination']['total_items'] >0:
            #have an ending for the neuron
            end_block = resJson1['data'][0]['block_number']
            end_time = resJson1['data'][0]['timestamp']
            emission = float(resJson1['data'][0]['emission'])/1e9
        #from events - ge the cost of registration
        #this is in rao- but 
        url2 = f"https://api.taostats.io/api/event/v1?extrinsic_id={extrinsic_id}"
        response2 = requests.get(url2, headers=headers)
        resJson2 = json.loads(response2.text)
        regcost=0
        events = resJson2['data']
        for event in events:
            if event['name'] =="Withdraw":
                regcost = float(event['args']['amount'])/1e9
        datetime_start = stupid_time_fix(start_time)
        datetime_end = stupid_time_fix(end_time)
        time_registered = (datetime_end - datetime_start)
        
        
        #now that we know how much tao was spent - what was the cost in dollars?
        url3 = f"https://api.taostats.io/api/price/history/v1?asset=tao&timestamp_start={start_time}&timestamp_end={end_time}&limit=1&order=timestamp_asc"
        response3 = requests.get(url3, headers=headers)
        resJson3 = json.loads(response3.text)
        price = float(resJson3['data'][0]['price'])
        regspent = regcost*price
        
        
        temp = {"netuid":netuid, 
                 "ck":coldkey, 
                 "hk":hotkey, 
                 "extrinsic": extrinsic_id, 
                 "block_start":start_block, 
                 "block_end":end_block, 
                 "start_time": start_time, 
                "end_time":end_time,
                "registered_time":time_registered, 
                "price":price,
                "reg_cost":regcost,
                 "reg_spent":regspent}
        print(temp)
        neuron_registration_data.append(temp)
        #no need to get rate limited
        time.sleep(9)

    

# %%
print(len(neuron_registration_data))

# %%
#ok, I have all the registration data
all_times = []
all_costs = []
all_prices =[]
for reg in neuron_registration_data:
    all_times.append(reg['registered_time'])
    all_costs.append(reg['reg_cost'])
    all_prices.append(reg['reg_spent'])
total_tao_cost = 0
total_spend =0
for cost in all_costs:
    total_tao_cost += cost
for price in all_prices:
    total_spend+=price
print(total_tao_cost, total_spend)

# %%
import numpy as np

numbers = [12, 45, 7, 23, 56, 89, 34]

# Minimum
min_value = np.min(all_times)
print("Minimum:", min_value)

# Maximum
max_value = np.max(all_times)
print("Maximum:", max_value)

# Average
average = np.mean(all_times)
print("Average:", average)

# Median
median = np.median(all_times)
print("Median:", median)

# Standard Deviation
std_dev = np.std(all_times)
print("Standard Deviation:", std_dev)


# %%
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import datetime as dt
data = neuron_registration_data
fig, ax = plt.subplots(figsize=(10, 6))

# Create a dictionary to store the hotkey indices
hotkey_indices = {}
index = 0
for item in data:
    if item['hk'] not in hotkey_indices:
        hotkey_indices[item['hk']] = index
        index += 1

fig, ax = plt.subplots(figsize=(10, 6))

for item in data:
    start_time = stupid_time_fix(item['start_time'])
    end_time = stupid_time_fix(item['end_time'])
    duration = (end_time - start_time).total_seconds() / 3600  # convert to hours
    hotkey_index = hotkey_indices[item['hk']]
    ax.barh(hotkey_index, width=duration, left=start_time, color='blue', alpha=0.5)

ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))  # show only Mondays
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
ax.set_yticks(range(len(hotkey_indices)))
ax.set_yticklabels(hotkey_indices.keys())
ax.set_xlabel('Date')
ax.set_ylabel('Hotkey')
ax.set_title('Start and End Times')

plt.show()

# %%



