import yaml
import os

def load_yaml(filename):
    if not str(filename).endswith(".yml"):
        raise ValueError("Filename must end with .yaml")
    
    if not os.path.exists(filename):
        raise FileNotFoundError(f"File '{filename}' does not exist")
    
    with open(filename, "r") as f:
        data = yaml.safe_load(f)
        print(data)
    
    if not isinstance(data, dict):
        raise ValueError("YAML content must be a dictionary",data)

    return data
