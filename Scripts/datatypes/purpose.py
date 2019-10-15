import parameters as param
import models.logit as logit
import models.generation as generation
from datatypes.demand import Demand
import numpy
import pandas

class Purpose:
    def __init__(self, specification, zone_data):
        """Generic container class without methods.
        Sets the purpose zone bounds.

        Parameters
        ----------
        specification : dict
            "name" : str
                Tour purpose name
            "orig" : str
                Origin of the tours
            "dest" : str
                Destination of the tours
            "area" : str
                Model area
        zone_data : ZoneData
            Data used for all demand calculations
        """
        self.name = specification["name"]
        self.orig = specification["orig"]
        self.dest = specification["dest"]
        self.area = specification["area"]
        self.sources = []
        if self.area == "metropolitan":
            l = 0
            u = zone_data.first_peripheral_zone
        if self.area == "peripheral":
            l = zone_data.first_peripheral_zone
            u = zone_data.nr_zones
        if self.area == "all":
            l = 0
            u = zone_data.nr_zones
        if self.area == "external":
            l = zone_data.first_external_zone
            u = None
        self.bounds = (l, u)
        self.zone_data = zone_data
        self.generated_tours = {}
        self.attracted_tours = {}


class TourPurpose(Purpose):
    def __init__(self, specification, zone_data):
        """Standard two-way tour purpose.

        Parameters
        ----------
        specification : dict
            "name" : str
                Tour purpose name (hw/oo/hop/sop/...)
            "orig" : str
                Origin of the tours (home/source)
            "dest" : str
                Destination of the tours (work/other/source/...)
            "area" : str
                Model area (metropolitan/peripheral)
        zone_data : ZoneData
            Data used for all demand calculations
        """
        Purpose.__init__(self, specification, zone_data)
        if self.orig == "source":
            self.gen_model = generation.NonHomeGeneration(zone_data, self)
        else:
            self.gen_model = generation.GenerationModel(zone_data, self)
        if self.name == "sop":
            self.model = logit.OriginModel(zone_data, self)
        elif self.name == "so":
            self.model = logit.DestModeModel(zone_data, self)
        else:
            self.model = logit.ModeDestModel(zone_data, self)
        self.modes = self.model.mode_choice_param.keys()

    def calc_demand(self, impedance):
        """Main method for purpose specific demand calculation.
        
        Parameters
        ----------
        impedance : dict
            Mode (car/transit/bike/walk) : dict
                Type (time/cost/dist) : numpy 2d matrix
        
        Return
        ------
        dict
            Mode (car/transit/bike) : dict
                Demand matrix for whole day : Demand
        """
        tours = self.gen_model.generate_tours()
        prob = self.model.calc_prob(impedance)
        demand = {}
        self.demand = {}
        self.aggregated_demand = {}
        for mode in self.model.mode_choice_param:
            self.demand[mode] = (prob[mode] * tours).T
            demand[mode] = Demand(self, mode, self.demand[mode])
            self.attracted_tours[mode] = self.demand[mode].sum(0)
            self.generated_tours[mode] = self.demand[mode].sum(1)
            self.aggregated_demand[mode] = self._aggregate(self.demand[mode])
        return demand

    def _aggregate(self, mtx):
        """Aggregate matrix to larger areas."""
        dest = self.zone_data.zone_numbers
        orig = self.zone_data.zone_numbers[self.bounds[0]:self.bounds[1]]
        mtx = pandas.DataFrame(mtx, orig, dest)
        idx = param.areas.keys()
        aggr_mtx = pandas.DataFrame(0, idx, idx)
        tmp_mtx = pandas.DataFrame(0, idx, dest)
        for area in param.areas:
            l = param.areas[area][0]
            u = param.areas[area][1]
            tmp_mtx.loc[area] = mtx.loc[l:u].sum(0).values
        for area in param.areas:
            l = param.areas[area][0]
            u = param.areas[area][1]
            aggr_mtx.loc[:, area] = tmp_mtx.loc[:, l:u].sum(1).values
        return aggr_mtx


class SecDestPurpose(Purpose):
    def __init__(self, specification, zone_data):
        """Purpose for secondary destination of tour.

        Parameters
        ----------
        specification : dict
            "name" : str
                Tour purpose name (hoo)
            "orig" : str
                Origin of the tours (home)
            "dest" : str
                Destination of the tours (any)
            "area" : str
                Model area (metropolitan)
        zone_data : ZoneData
            Data used for all demand calculations
        """
        Purpose.__init__(self, specification, zone_data)
        self.gen_model = generation.SecDestGeneration(zone_data, self)
        self.model = logit.SecDestModel(zone_data, self)

    def generate_tours(self):
        """Generate the source tours without secondary destinations."""
        self.tours = {}
        for mode in self.model.dest_choice_param:
            self.tours[mode] = self.gen_model.generate_tours(mode)
            self.attracted_tours[mode] = self.tours[mode].sum(0)
            self.generated_tours[mode] = self.tours[mode].sum(1)

    def distribute_tours(self, mode, impedance, origin):
        """Decide the secondary destination for all tours (generated 
        earlier) starting from one specific zone.
        
        Parameters
        ----------
        mode : str
            Mode (car/transit/bike)
        impedance : dict
            Type (time/cost/dist) : numpy 2d matrix
        origin : int
            The zone from which these tours origin

        Return
        ------
        Demand
            Matrix of destination -> secondary_destination pairs
            The origin zone for all of these tours
        """
        dest_imp = {}
        for mtx_type in impedance:
            dest_imp[mtx_type] = ( impedance[mtx_type]
                                 + impedance[mtx_type][:, origin]
                                 - impedance[mtx_type][origin, :][:, numpy.newaxis])
        prob = self.model.calc_prob(mode, dest_imp)
        demand = (prob * self.tours[mode][origin, :]).T
        self.attracted_tours[mode] += demand.sum(0)
        return Demand(self, mode, demand, origin)

    def calc_prob(self, mode, impedance, position):
        """Calculate secondary destination probabilites for tours
        starting and ending in two specific zones.
        Method used in agent-based simulation.
        
        Parameters
        ----------
        mode : str
            Mode (car/transit/bike)
        impedance : dict
            Type (time/cost/dist) : numpy 2d matrix
        position : tuple
            int
                Origin zone
            int
                Destination zone

        Return
        ------
        numpy 1-d array
            Probability vector for chosing zones as secondary destination
        """
        orig = position[0]
        dest = position[1]
        dest_imp = {}
        for mtx_type in impedance:
            dest_imp[mtx_type] = ( impedance[mtx_type][dest, :]
                                 + impedance[mtx_type][:, orig]
                                 - impedance[mtx_type][orig, dest])
        return self.model.calc_prob(mode, dest_imp)