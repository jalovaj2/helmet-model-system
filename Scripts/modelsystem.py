from utils.log import Log
import assignment.departure_time as dt
from datahandling.resultdata import ResultsData
from datahandling.zonedata import ZoneData, BaseZoneData
from datahandling.matrixdata import MatrixData
from demand.freight import FreightModel
from demand.trips import DemandModel
from demand.external import ExternalModel
from datatypes.purpose import SecDestPurpose
from transform.impedance_transformer import ImpedanceTransformer
from models.linear import CarDensityModel
import parameters
import numpy
import pandas
import threading
import multiprocessing
import os


class ModelSystem:
    def __init__(self, zone_data_path, base_zone_data_path, base_matrices_path, results_path, ass_model, name):
        self.logger = Log.get_instance()
        self.ass_model = ass_model
        # Input data
        self.zdata_base = BaseZoneData(base_zone_data_path, ass_model.zone_numbers)
        self.basematrices = MatrixData(base_matrices_path)
        self.zdata_forecast = ZoneData(zone_data_path, ass_model.zone_numbers)
        # Output data
        self.resultmatrices = MatrixData(os.path.join(results_path, name, "Matrices"))
        self.resultdata = ResultsData(os.path.join(results_path, name))

        self.dm = self._init_demand_model()

        self.fm = FreightModel(self.zdata_base,
                               self.zdata_forecast,
                               self.basematrices)
        self.em = ExternalModel(self.basematrices,
                                self.zdata_forecast,
                                self.ass_model.zone_numbers)
        self.dtm = dt.DepartureTimeModel(self.ass_model.nr_zones)
        self.imptrans = ImpedanceTransformer()
        bounds = slice(0, self.zdata_forecast.nr_zones)
        self.cdm = CarDensityModel(self.zdata_base, self.zdata_forecast, bounds, self.resultdata)
        # TODO: Should be better defined as parameter when we don't  
        # have different transit matrices as input data. 
        # Could use this list_matrices as input validation.
        self.ass_classes = self.basematrices.list_matrices("demand", "aht")
        self.mode_share = []
        self.trucks = self.fm.calc_freight_traffic("truck")
        self.trailer_trucks = self.fm.calc_freight_traffic("trailer_truck")

    def _init_demand_model(self):
        return DemandModel(self.zdata_forecast, self.resultdata, is_agent_model=False)

    def _add_internal_demand(self, previous_iter_impedance, is_last_iteration):
        self.dm.create_population_segments()
        for purpose in self.dm.tour_purposes:
            if isinstance(purpose, SecDestPurpose):
                purpose.gen_model.init_tours()
            else:
                purpose_impedance = self.imptrans.transform(purpose, previous_iter_impedance)
                purpose.calc_prob(purpose_impedance)
        self.dm.generate_tours()
        for purpose in self.dm.tour_purposes:
            if isinstance(purpose, SecDestPurpose):
                purpose_impedance = self.imptrans.transform(purpose, previous_iter_impedance)
                purpose.generate_tours()
                if is_last_iteration:
                    for mode in purpose.model.dest_choice_param:
                        self._distribute_sec_dests(purpose, mode, purpose_impedance)
                else:
                    self._distribute_sec_dests(purpose, "car", purpose_impedance)
            else:
                demand = purpose.calc_demand()
                if purpose.dest != "source":
                    for mode in demand:
                        self.dtm.add_demand(demand[mode])

    # possibly merge with init
    def assign_base_demand(self, use_fixed_transit_cost=False):
        impedance = {}

        # Calculate transit cost matrix, and save it to emmebank
        with self.basematrices.open("cost", "peripheral") as peripheral_mtx:
            peripheral_cost = peripheral_mtx["transit"]
            if use_fixed_transit_cost:
                self.logger.info("Using fixed transit cost matrix")
                with self.basematrices.open("cost", "aht") as aht_mtx:
                    fixed_cost = aht_mtx["transit"]
            else:
                self.logger.info("Calculating transit cost")
                fixed_cost = None
            self.ass_model.calc_transit_cost(self.zdata_forecast.transit_zone, peripheral_cost, fixed_cost)

        # Perform traffic assignment and get result impedance, for each time period
        for tp in parameters.emme_scenario:
            self.logger.info("Assigning period " + tp)
            with self.basematrices.open("demand", tp) as mtx:
                for ass_class in self.ass_classes:
                    self.dtm.demand[tp][ass_class] = mtx[ass_class]
            self.ass_model.assign(tp, self.dtm.demand[tp])
            impedance[tp] = self.ass_model.get_impedance()
            if tp == "aht":
                self._update_ratios(impedance, tp)
        return impedance

    def run_iteration(self, previous_iter_impedance, is_last_iteration=False):
        impedance = {}

        # Add truck and trailer truck demand, to time-period specific matrices (DTM), used in traffic assignment
        self.dtm.add_demand(self.trucks)
        self.dtm.add_demand(self.trailer_trucks)

        # Update car density
        prediction = self.cdm.predict()
        self.zdata_forecast["car_density"] = prediction
        self.zdata_forecast["cars_per_1000"] = 1000 * prediction

        self._add_internal_demand(previous_iter_impedance, is_last_iteration)

        # Calculate external demand
        trip_sum = {}
        for mode in parameters.external_modes:
            if mode == "truck":
                int_demand = self.trucks.matrix.sum(0) + self.trucks.matrix.sum(1)
            elif mode == "trailer_truck":
                int_demand = self.trailer_trucks.matrix.sum(0) + self.trailer_trucks.matrix.sum(1)
            else:
                nr_zones = len(self.zdata_base.zone_numbers)
                int_demand = numpy.zeros(nr_zones)
                for purpose in self.dm.tour_purposes:
                    if purpose.dest != "source":
                        if isinstance(purpose, SecDestPurpose):
                            bounds = next(iter(purpose.sources)).bounds
                        else:
                            bounds = purpose.bounds
                        int_demand[bounds] += purpose.generated_tours[mode]
                        int_demand += purpose.attracted_tours[mode]
            ext_demand = self.em.calc_external(mode, int_demand)
            trip_sum[mode] = int_demand.sum()
            self.dtm.add_demand(ext_demand)
        sum_all = sum(trip_sum.values())
        mode_share = {}
        for mode in trip_sum:
            mode_share[mode] = trip_sum[mode] / sum_all
        self.mode_share.append(mode_share)

        # Calculate and return traffic impedance
        for tp in parameters.emme_scenario:
            self.dtm.add_vans(tp, self.zdata_forecast.nr_zones)
            self.ass_model.assign(tp, self.dtm.demand[tp], is_last_iteration)
            impedance[tp] = self.ass_model.get_impedance(is_last_iteration)

            # Car Ownership -model specific block
            if tp == "aht":
                self._update_ratios(impedance, tp)
            
            if is_last_iteration:
                zone_numbers = self.ass_model.zone_numbers
                with self.resultmatrices.open("demand", tp, 'w') as mtx:
                    mtx.mapping = zone_numbers
                    for ass_class in self.dtm.demand[tp]:
                        mtx[ass_class] = self.dtm.demand[tp][ass_class]
                    self.logger.info("Saved demand matrices for " + str(tp))
                for mtx_type in impedance[tp]:
                    with self.resultmatrices.open(mtx_type, tp, 'w') as mtx:
                        mtx.mapping = zone_numbers
                        for ass_class in impedance[tp][mtx_type]:
                            cost_data = impedance[tp][mtx_type][ass_class]
                            mtx[ass_class] = cost_data

        if is_last_iteration:
            self.ass_model.print_vehicle_kms(self.resultdata)

        # Reset time-period specific demand matrices (DTM), and empty result buffer
        self.dtm.init_demand()
        self.resultdata.flush()
        return impedance

    def _distribute_sec_dests(self, purpose, mode, impedance):
        threads = []
        demand = []
        nr_threads = parameters.performance_settings["number_of_processors"]
        if nr_threads == "max":
            nr_threads = multiprocessing.cpu_count()
        elif nr_threads <= 0:
            nr_threads = 1
        bounds = next(iter(purpose.sources)).bounds
        split = (bounds.stop-bounds.start) // nr_threads
        for i in xrange(0, nr_threads):
            # Take a chunk of destinations, for which this thread
            # will calculate secondary destinations
            start = bounds.start + i*split
            if i+1 < nr_threads:
                dests = xrange(start, start + split)
            else:
                dests = xrange(start, bounds.stop)
            # Results will be saved in a temp dtm, to avoid memory clashes
            dtm = dt.DepartureTimeModel(self.ass_model.nr_zones)
            demand.append(dtm)
            thread = threading.Thread(
                target=self._distribute_tours,
                args=(dtm, purpose, mode, impedance, dests))
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()
        for dtm in demand:
            for tp in dtm.demand:
                for ass_class in dtm.demand[tp]:
                    self.dtm.demand[tp][ass_class] += dtm.demand[tp][ass_class]

    def _distribute_tours(self, container, purpose, mode, impedance, dests):
        for i in dests:
            demand = purpose.distribute_tours(mode, impedance[mode], i)
            container.add_demand(demand)

    def _update_ratios(self, impedance, tp):
        """Calculate time and cost ratios.
        
        Parameters
        ----------
        impedance : dict
            Impedance matrices.
        tp : str
            TIme period (usually aht in this function).
        """ 
        car_time = numpy.ma.average(
            impedance[tp]["time"]["car_work"], axis=1,
            weights=self.dtm.demand[tp]["car_work"])
        transit_time = numpy.ma.average(
            impedance[tp]["time"]["transit"], axis=1,
            weights=self.dtm.demand[tp]["transit_work"])
        time_ratio = transit_time / car_time
        self.resultdata.print_data(
            time_ratio, "impedance_ratio.txt",
            self.ass_model.zone_numbers, "time")
        self.zdata_forecast["time_ratio"] = pandas.Series(
            numpy.ma.getdata(time_ratio), self.ass_model.zone_numbers)
        car_cost = numpy.ma.average(
            impedance[tp]["cost"]["car_work"], axis=1,
            weights=self.dtm.demand[tp]["car_work"])
        transit_cost = numpy.ma.average(
            impedance[tp]["cost"]["transit"], axis=1,
            weights=self.dtm.demand[tp]["transit_work"])
        cost_ratio = transit_cost / 44. / car_cost
        cost_ratio = cost_ratio.clip(0.01, None)
        self.resultdata.print_data(
            cost_ratio, "impedance_ratio.txt",
            self.ass_model.zone_numbers, "cost")
        self.zdata_forecast["cost_ratio"] = pandas.Series(
            numpy.ma.getdata(cost_ratio), self.ass_model.zone_numbers)


class AgentModelSystem(ModelSystem):

    def _init_demand_model(self):
        return DemandModel(self.zdata_forecast, self.resultdata, is_agent_model=True)

    def _add_internal_demand(self, previous_iter_impedance, is_last_iteration):
        self.dm.create_population()
        for purpose in self.dm.tour_purposes:
            if isinstance(purpose, SecDestPurpose):
                purpose.init_sums()
            else:
                purpose_impedance = self.imptrans.transform(purpose, previous_iter_impedance)
                if purpose.area == "peripheral" or purpose.name == "oop":
                    purpose.calc_prob(purpose_impedance)
                    purpose.gen_model.init_tours()
                    purpose.gen_model.add_tours()
                    demand = purpose.calc_demand()
                    if purpose.dest != "source":
                        for mode in demand:
                            self.dtm.add_demand(demand[mode])
                else:
                    purpose.init_sums()
                    purpose.model.calc_basic_prob(purpose_impedance)
        purpose_impedance = self.imptrans.transform(self.dm.purpose_dict["hoo"], previous_iter_impedance)
        for person in self.dm.population:
            person.add_tours(self.dm.purpose_dict)
            for tour in person.tours:
                tour.choose_mode(person.is_car_user)
                tour.choose_destination(purpose_impedance)
                if tour.mode == "car":
                    tour.choose_driver()
                self.dtm.add_demand(tour)
