import os
import omx
import numpy
import pandas
import parameters as param

class MatrixData:
    def __init__(self, scenario):
        script_dir = os.path.dirname(os.path.realpath('__file__'))
        project_dir = os.path.join(script_dir, "..")
        self.path = os.path.join(project_dir, "Matrices", scenario)
    
    def open_file(self, mtx_type, time_period, m='r'):
        file_name = os.path.join(self.path, mtx_type+'_'+time_period+".omx")
        self.mtx_file = omx.openFile(file_name, m)
    
    def close(self):
        self.mtx_file.close()
    
    def get_data(self, mode):
        return numpy.array(self.mtx_file[mode])

    def get_external(self, mode):
        return read_file(self.path, "external_"+mode+".csv")

    def set_data(self, data, mode):
        self.mtx_file[mode] = data

    def get_zone_numbers(self):
        # zone_numbers = mtx_file.mapentries("zone_number")
        zone_numbers = self.mtx_file.mapping("zone_number").keys()
        zone_numbers.sort()
        return zone_numbers

    def get_mapping(self):
        mapping = self.mtx_file.mapping("zone_number")
        return mapping

    def set_mapping(self, zone_numbers):
        self.mtx_file.createMapping("zone_number", zone_numbers)

class ZoneData:
    def __init__(self, scenario):
        script_dir = os.path.dirname(os.path.realpath('__file__'))
        project_dir = os.path.join(script_dir, "..")
        data_dir = os.path.join(project_dir, "Zone_data", scenario)
        popdata = read_file(data_dir, "population.txt")
        workdata = read_file(data_dir, "workplaces.txt")
        schooldata = read_file(data_dir, "schools.txt")
        landdata = read_file(data_dir, "land.txt")
        self.externalgrowth = read_file(data_dir, "external.txt")
        transit_zone = read_file(data_dir, "transit_cost.txt").to_dict()
        transit_zone["dist_fare"] = transit_zone["fare"].pop("dist")
        transit_zone["start_fare"] = transit_zone["fare"].pop("start")
        self.transit_zone = transit_zone
        car_cost = read_file(data_dir, "car_cost.txt", True)
        self.car_dist_cost = car_cost[0]
        val = {}
        pop = popdata["total"]
        val["population"] = pop
        self.zone_numbers = pop.index
        self.nr_zones = len(self.zone_numbers)
        val["population_density"] = pop/ landdata["builtar"]
        val["car_density"] = popdata["cardens"]
        wp = workdata["total"]
        val["workplaces"] = wp
        val["service"] = workdata["sh_serv"] * wp
        val["shops"] = workdata["sh_shop"] * wp
        val["logistics"] = workdata["sh_logi"] * wp
        val["industry"] = workdata["sh_indu"] * wp
        val["parking_cost"] = workdata["parcosw"]
        val["comprehensive_schools"] = schooldata["compreh"]
        val["secondary_schools"] = schooldata["secndry"]
        val["tertiary_education"] = schooldata["tertiary"]
        val["zone_area"] = landdata["builtar"]
        val["share_detached_houses"] = landdata["detach"]
        val["downtown"] = pandas.Series(0, self.zone_numbers)
        val["downtown"].loc[:999] = 1
        # capital_region = pandas.Series(0, self.zone_numbers)
        # capital_region.loc[:5999] = 1
        val["shops_downtown"] = val["downtown"] * val["shops"]
        val["shops_elsewhere"] = (1-val["downtown"]) * val["shops"]
        # Create diagonal matrix with zone area
        di = numpy.diag_indices(self.nr_zones)
        val["own_zone_area"] = numpy.zeros((self.nr_zones, self.nr_zones))
        val["own_zone_area"][di] = val["zone_area"]
        val["own_zone_area_sqrt"] = numpy.sqrt(val["own_zone_area"])
        # Create matrix where value is 1 if origin and destination is in
        # same municipality
        idx = self.zone_numbers
        home_municipality = pandas.DataFrame(0, idx, idx)
        municipalities = param.municipality
        for municipality in municipalities:
            l = municipalities[municipality][0]
            u = municipalities[municipality][1]
            home_municipality.loc[l:u, l:u] = 1
        val["population_own"] = home_municipality.values * pop.values
        val["population_other"] = (1-home_municipality.values) * pop.values
        val["workplaces_own"] = home_municipality.values * wp.values
        val["workplaces_other"] = (1-home_municipality.values) * wp.values
        self.values = val

    def get_freight_data(self):
        freight_variables = (
            "population",
            "workplaces",
            "shops",
            "logistics",
            "industry",
        )
        data = {k: self.values[k] for k in freight_variables}
        return pandas.DataFrame(data)

    def get_data(self, data_type, purpose, generation=False, part=None):
        l, u = self.get_bounds(purpose)
        k = self.zone_numbers.get_loc(param.first_surrounding_zone)
        if self.values[data_type].ndim == 1:
            if generation:
                if part is None:
                    return self.values[data_type][l:u]
                elif part == 0:
                    return self.values[data_type][l:k]
                else:
                    return self.values[data_type][k:u]
            else:
                return self.values[data_type]
        if part is None:
            return self.values[data_type][l:u, :]
        elif part == 0:
            return self.values[data_type][:k, :]
        else:
            return self.values[data_type][k:u, :]

    def get_bounds(self, purpose):
        if purpose.area == "metropolitan":
            l = 0
            u_label = param.first_peripheral_zone
            u = self.zone_numbers.get_loc(u_label)
        if purpose.area == "peripheral":
            l_label = param.first_peripheral_zone
            l = self.zone_numbers.get_loc(l_label)
            u = len(self.zone_numbers)
        if purpose.area == "all":
            l = 0
            u = len(self.zone_numbers)
        return l, u

def read_file(data_dir, file_name, squeeze=False):
    path = os.path.join(data_dir, file_name)
    return pandas.read_csv(filepath_or_buffer=path, 
                            delim_whitespace=True,
                            keep_default_na=False,
                            squeeze=squeeze,
                            comment='#')