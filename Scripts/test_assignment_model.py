import os
import omx
import numpy
import parameters as param
from assignment_model import AssignmentModel

class TestAssignmentModel:
    def __init__(self, matrix_dir):
        self.path = matrix_dir
    
    def assign(self, time_period, matrices):
        """Get travel impedance matrices for one time period from files."""
        mtxs = {}
        mtxs["time"] = self.get_matrices(time_period, "time")
        mtxs["cost"] = self.get_matrices(time_period, "cost")
        mtxs["dist"] = self.get_matrices(time_period, "dist")
        return mtxs
    
    def get_matrices(self, mtx_type, time_period):
        file_name = os.path.join(self.path, mtx_type+'_'+time_period+".omx")
        costs_file = omx.openFile(file_name)
        matrices = dict.fromkeys(param.emme_mtx[mtx_type].keys())
        for mtx in matrices:
            matrices[mtx] = numpy.array(costs_file[mtx])
        costs_file.close()
        return matrices
    
    def get_zone_numbers(self):
        file_name = os.path.join(self.path, "time_aht.omx")
        costs_file = omx.openFile(file_name)
        # zone_numbers = costs_file.mapentries("zone_number")
        zone_numbers = [5, 6, 7]
        costs_file.close()
        return zone_numbers
    
    def get_mapping(self):
        file_name = os.path.join(self.path, "time_aht.omx")
        costs_file = omx.openFile(file_name)
        mapping = costs_file.mapping("zone_number")
        costs_file.close()
        return mapping

AssignmentModel.register(TestAssignmentModel)