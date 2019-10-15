import os
import json

class Config():
    
    SCENARIO_NAME = 'SCENARIO_NAME'
    ITERATION_COUNT = 'ITERATION_COUNT'
    USE_EMME = 'USE_EMME'
    LOG_LEVEL = 'LOG_LEVEL'
    LOG_FORMAT = 'LOG_FORMAT'
    DATA_PATH = 'DATA_PATH'
    EMME_PROJECT_PATH = 'EMME_PROJECT_PATH'
    USE_FIXED_TRANSIT_COST = 'USE_FIXED_TRANSIT_COST'

    DefaultScenario = "helmet"

    def __init__(self):
        self.__config = {}

    @staticmethod
    def read_from_file(path="dev-config.json"):
        print 'reading configuration from file "{}"'.format(path)
        instance = Config()

        with open(path, 'r') as f:
            instance.__config = json.load(f)

        print 'read {} config variables'.format(len(instance.__config))
        return instance

    def get_value(self, key):
        from_env = os.environ.get(key, None)
        if from_env:
            return from_env
        else:
            return self.__config[key]

    def set_value(self, key, value):
        self.__config[key] = value