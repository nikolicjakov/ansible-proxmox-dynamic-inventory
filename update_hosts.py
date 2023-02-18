import proxmoxer
import json
import yaml
import logging
import requests.exceptions
import time
import os
import urllib3

def fetch_vm_data(nodes):
    # Fetch the network interface information for all available virtual machines on each node
    vm_data = {}
    with open('failed-vm.log', 'w') as f:
        for node in nodes:
            vms = proxmox.nodes(node).qemu.get()
            for vm in vms:
                vm_id = vm['vmid']
                agent = proxmox.nodes(node).qemu(vm_id).agent()
                retry_count = 0
                while True:
                    try:
                        response = agent.get('network-get-interfaces')
                        break
                    except requests.exceptions.ReadTimeout as e:
                        if retry_count < 5:
                            print(f"Retrying VM {vm['name']} (VMID: {vm_id}) after {e} (retry count: {retry_count + 1})")
                            retry_count += 1
                            time.sleep(3)
                        else:
                            f.write(f"{vm['name']} (ID: {vm_id}) - {e}\n")
                            #print(f"Skipping VM {vm['name']} (VMID: {vm_id}) due to error: {str(e)}")
                            response = None
                            break
                    except proxmoxer.core.ResourceException as e:
                        f.write(f"{vm['name']} (ID: {vm_id}) - {e}\n")
                        #print(f"Skipping VM {vm['name']} (VMID: {vm_id}) due to error: {str(e)}")
                        response = None
                        break
                if response:
                    interfaces = response.get('result', [])
                    ip_addresses = []
                    for interface in interfaces:
                        if 'ip-addresses' in interface:
                            for address in interface['ip-addresses']:
                                ip_address = address.get('ip-address')
                                if ip_address and ip_address.startswith(ip_prefix):
                                    ip_addresses.append(ip_address)
                    if ip_addresses:
                        print(f"VM: {vm['name']} added to the inventory.\n")
                        vm_data[vm['name']] = {'ansible_host': ip_addresses[0]}
                    else:
                        f.write(f"{vm['name']} (VMID: {vm_id})\n")
                        #print(f"Skipping VM {vm['name']} (VMID: {vm_id}) because no valid IP address was found")
                        continue
        return vm_data

def write_vm_data_to_json_file(vm_data, json_filename):
    # Write the virtual machine data (including network interface information) to a JSON file
    with open(json_filename, 'w') as f:
        json.dump(vm_data, f)

def write_vm_data_to_yaml_file(vm_data, yaml_filename):
    # Write the virtual machine data (including network interface information) to a YAML file in the desired format
    output = {'all': {'hosts': {}, 'children': {'vms': {'hosts': vm_data}}}}
    with open(yaml_filename, 'w') as f:
        yaml.dump(output, f, default_flow_style=False, explicit_start=True)

def remove_empty_hosts(yaml_filename):
    # Read the YAML file and replace the `hosts: {}` line with `hosts:`
    with open(yaml_filename, 'r') as f:
        yaml_file = f.read()
    yaml_file = yaml_file.replace('hosts: {}', 'hosts:')
    with open(yaml_filename, 'w') as f:
        f.write(yaml_file)

def print_motd():
    print("""
   _  __    ____  __            ___                                      _____                      _                       ___                          _             
  /_\/ / /\ \ \ \/ /           / _ \_ __ _____  ___ __ ___   _____  __   \_   \_ ____   _____ _ __ | |_ ___  _ __ _   _    / _ \___ _ __   ___ _ __ __ _| |_ ___  _ __ 
 //_\\\ \/  \/ /\  /   _____   / /_)| '__/ _ \ \/ | '_ ` _ \ / _ \ \/ /    / /\| '_ \ \ / / _ | '_ \| __/ _ \| '__| | | |  / /_\/ _ | '_ \ / _ | '__/ _` | __/ _ \| '__|
/  _  \  /\  / /  \  |_____| / ___/| | | (_) >  <| | | | | | (_) >  <  /\/ /_ | | | \ V |  __| | | | || (_) | |  | |_| | / /_\|  __| | | |  __| | | (_| | || (_) | |   
\_/ \_/\/  \/ /_/\_\         \/    |_|  \___/_/\_|_| |_| |_|\___/_/\_\ \____/ |_| |_|\_/ \___|_| |_|\__\___/|_|   \__, | \____/\___|_| |_|\___|_|  \__,_|\__\___/|_|   
                                                                                                                  |___/                                                
Author: Jakov Nikolić
""")


if __name__ == '__main__':
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    # Suppress InsecureRequestWarning from urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    logging.getLogger('urllib3').setLevel(logging.WARNING)

    # Get the value of the environment variables, or use default values if they are not defined
    proxmox_url = os.getenv('PROXMOX_URL', 'proxmox.example.com')
    proxmox_user = os.getenv('PROXMOX_USER', 'root@pam')
    proxmox_password = os.getenv('PROXMOX_PASSWORD', 'changeme')
    proxmox_nodes = os.getenv('PROXMOX_NODES', 'node1,node2,node3')
    ip_prefix = os.getenv('IP_PREFIX', '192.168.')

    # Connect to the Proxmox cluster
    proxmox = proxmoxer.ProxmoxAPI(proxmox_url, user=proxmox_user, password=proxmox_password, verify_ssl=False)

    # Define the list of nodes to query
    nodes = proxmox_nodes.split(',')

    print_motd()
    vm_data = fetch_vm_data(nodes)
    write_vm_data_to_json_file(vm_data, 'vms_with_network_info.json')
    write_vm_data_to_yaml_file(vm_data, 'hosts')
    remove_empty_hosts('hosts')