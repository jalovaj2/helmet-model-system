from utils.config import Config
from utils.log import Log
import os

class HelmetApplication():

    def __init__(self, config):
        self.__config = config
        self.logger = Log.get_instance()
        if config.get_value(Config.KEY_USE_EMME):
            self.logger.info("Configuration set to use EMME, initializing")
            self.initialize_EMME()
        else:
            self.logger.info("Configuration NOT using EMME")
            

    
    def start_estimation(self):

        if not self.validate_input():
            self.logger.error("Failed to validate input, aborting estimation")
            return

        iterations = self.__config.get_value(Config.KEY_ITERATION_COUNT)
        self.logger.info("Start estimation loop with {} iterations".format(self.__config.get_value(Config.KEY_ITERATION_COUNT)))
        for round in range(1, iterations+1):
            try:
                self.logger.info("Starting round {}".format(round))
            except Exception as error:
                is_fatal = self.handle_error("Exception at estimation round {}".format(round), error)
                if is_fatal:
                    self.logger.error("Fatal error occured, stopping estimation loop")
                    break

        self.logger.info("All done, thank you!")

    def handle_error(self, msg, exception):
        self.logger.error(msg, exception)
        fatal = True
        return fatal


    def validate_input(self):
        # TODO read the scenario from parameters / config and read input data & validate it
        return True

    def initialize_EMME(self):
        #TODO figure out if we only need to do this once in the beginning or between simulations?
        from emme.emme_context import EmmeContext

        script_dir = os.path.dirname(os.path.realpath('__file__'))
        project_dir = os.path.join(script_dir, "..")
        for file_name in os.listdir(project_dir):
            if file_name.endswith(".emp"):
                empfile = os.path.join(project_dir, file_name)
        self.emme_context = EmmeContext(empfile)


# Main entry point for the application
if __name__ == "__main__":
    print "Initializing the application.."
    
    config = Config.read_from_file()
    Log.get_instance().initialize(config)
    
    Log.get_instance().info("Launching application")
    
    app = HelmetApplication(config)
    app.start_estimation()