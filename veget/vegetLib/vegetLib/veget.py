import os
import yaml
import sys

from .vegconfig import return_veget_params
from .rastermanager import RasterManager

class VegET:
    """
    This is the heart of the Veg ET model, a soil-water balance model.
    There are 3 main functions: soil_water, surface_runoff, veg_et which include the model calculations.
    """
    ### Atttributes = None, True False to start out.

    start_year = None
    end_year = None
    start_day = None
    end_day = None

    rf_low_thresh_temp = None
    rf_high_thresh_temp = None
    rf_value = None
    melt_factor = None
    dc_coeff = None
    rf_coeff = None
    k_factor = None
    ndvi_factor = None
    water_factor = None
    bias_corr = None
    alfa_factor = None

    geoproperties_file = None
    outdir = None
    accumulate_mode = None
    # ----- static soil rasters for model run------
    interception_settings = None
    whc_settings = None
    field_capacity_settings = None
    saturation_settings = None
    watermask_settings = None

    # dataset_configurations
    precip_settings = None
    ndvi_settings = None
    pet_settings = None
    tmin_settings = None
    tavg_settings = None
    tmax_settings = None

    def __init__(self, veget_config_path=None):
        
            # create an instance of the VegET model using the configurations from the file.
            self.config_dict = return_veget_params(veget_config_path)
            print('---'*30)
            # print(self.config_dict['start_day'])
            
            # set startday and endday
            # ===========run parameters===================
            self.start_day = self.config_dict['start_day']
            self.end_day = self.config_dict['end_day']
            self.start_year = self.config_dict['start_year']
            self.end_year = self.config_dict['end_year']
            
            # accumulation modes
            self.accumulate_mode = self.config_dict['accumulate_mode']
            
            # print(self.start_day, self.end_day, self.start_year, self.end_year)
            # print (self.accumulate_mode)
            
            # set here in init so they can be float
            # ====================== model parameters ==================================
            self.rf_low_thresh_temp = float(self.config_dict['rf_low_thresh_temp'])
            self.rf_high_thresh_temp = float(self.config_dict['rf_high_thresh_temp'])
            self.rf_value = float(self.config_dict['rf_value'])
            self.melt_factor = float(self.config_dict['melt_factor'])
            self.dc_coeff = float(self.config_dict['dc_coeff'])
            self.rf_coeff = float(self.config_dict['rf_coeff'])
            self.k_factor = float(self.config_dict['k_factor'])
            print(self.config_dict)
            print('---'*30)
            print(self.config_dict['start_day'])
            print(self.k_factor)
            sys.exit(0)
            self.ndvi_factor = float(self.config_dict.ndvi_factor)
            self.water_factor = float(self.config_dict.water_factor)
            self.bias_corr = float(self.config_dict.bias_corr)
            self.alfa_factor = float(self.config_dict.alfa_factor)


            
            
            # initialize the classes that manage Raster data and input/output paths to the data
            self.rmanager = RasterManager(config=self.config)
            sgrid = self.rmanager.set_model_std_grid(self)
            self.pmanager = PathManager(config=self.config)

            # set interception settings
            self.interception_settings = self.config.interception_settings
            self.whc_settings = self.config.whc_settings
            self.saturation_settings = self.config.saturation_settings
            self.watermask_settings = self.config.watermask_settings
            self.field_capacity_settings = self.config.field_capacity_settings
            self.ndvi_settings = self.config.ndvi_settings
            self.precip_settings = self.config.precip_settings
            self.pet_settings = self.config.pet_settings
            self.tavg_settings = self.config.tavg_settings
            self.tmin_settings = self.config.tmin_settings
            self.tmax_settings = self.config.tmax_settings

            

            # set the output dir and make it if it doens't exist
            self.outdir = self.config.out_root
            if not os.path.exists(self.outdir):
                os.makedirs(self.outdir)

    def _day_of_year(self, today):
        year = today.year
        print(year, today.month, today.day)
        DOY = '{:03d}'.format(today.timetuple().tm_yday)
        print(f'today is {DOY}')

        return DOY, year

    def _end_of_month(self, day, mon, year):
        #  calendar.monthrange return a tuple
        # (weekday of first day of the month, number of days in month)
        last_day_of_month = calendar.monthrange(year, mon)[1]
        # check if date is last day of month
        if date(year, mon, day) == date(year, mon, last_day_of_month):
            return True

        return False

    def _soil_water(self, i, ppt, interception, tmin, tmax, tavg, melt_factor, rf_high_thresh_temp, rf_low_thresh_temp,
                    yest_swf=None, yest_snwpck=None):

        """
        This function takes precipitation, interception, and temperature data to determine
        how much rain and snow was falling during that day's precipitation event, if there was
        snow, how much snow water equivalent was it, and what is the
        initial/starting soil water balance for the day after adding the water amount (rain/snow).
        :param SWi: initial/starting soil water balance for the day after adding the water amount (rain/snow)
        :param saturation: Soil saturation value (mm)
        :param field_capacity: field capacity value (mm) of soil
        :param whc: Water Holding Capacity (WHC) or available water content (AWC) (mm)
        :param rf_low_thresh_temp : 0 degree Celcius -> temperature below where precipitation is considered snow
        :param rf_high_thresh_temp : 6 degree Celcius -> temperature above where precipitation is considered rain
        :param rf_value : 0.167  slope value
        :param melt_factor : 0.06   from literature
        :return: SWi
        """

        # Check for no data value handling
        print('ppt min', np.min(ppt))
        print('ppt max', np.min(ppt))
        ppt[ppt <= -1] = np.nan
        ppt[ppt == 32767] = np.nan
        print('ppt min', np.min(ppt))
        print('ppt max', np.max(ppt))

        print('tavg min', np.min(tavg))
        tavg[tavg <= -100] = np.nan
        print('tavg min', np.min(tavg))
        tmax[tmax <= -100] = np.nan
        tmin[tmin <= -100] = np.nan

        # Effective precipitation
        effppt = ppt * (1 - (interception / 100.0))
        # Intercepted precipitation
        interception = ppt * (interception / 100.0)
        print('interception min', np.min(interception))

        # Snow pack
        # Usage: Creates a melt rate value based on the relationship between
        # max and min air temperature to determine the snow melt and from there the snow pack extent
        melt_rate = melt_factor * ((tmax * tmax) - (tmax - tmin))
        # initialize the snow melt factor array
        snow_melt_fac = np.zeros(ppt.shape)
        # where avg temp <= high_threshold_temp set to 0, else it is equal to the melt factor rate
        # (tavg <= rf_high_tresh_temp, 0, melt_rate)
        snow_melt_fac[tavg <= rf_high_thresh_temp] = melt_rate[tavg <= rf_high_thresh_temp]
        snow_melt_fac[tavg > rf_high_thresh_temp] = 0

        if i == 0:  # first day of model run to initalize and establish the soil water balance
            # Usage: Creates a fraction value based on average temperature that determines
            # if the incoming precipitation is falling as rain, sleet, or snow.
            # if tavg <= 0, make it 0, else if tavg >= 6, make it 1, else (0.167*(tavg-6))
            rain_frac = np.zeros(ppt.shape)
            rain_frac[tavg <= rf_low_thresh_temp] = 0
            rain_frac[tavg >= rf_high_thresh_temp] = 1
            temp_diff_boolean = (tavg < rf_high_thresh_temp) | (tavg > rf_low_thresh_temp)
            rain_frac[temp_diff_boolean] = self.rf_value * (tavg[temp_diff_boolean] - rf_high_thresh_temp)

            RAIN = rain_frac * effppt
            SWE = np.zeros(ppt.shape)  # inital snowpack raster with only 0 values
            snow_melt = SWE
            SNWpk = np.zeros(ppt.shape)  # inital snowpack raster with only 0 values
            SWi = (self.whc * 0.5) + effppt + snow_melt
            SWi[SWi < 0] = np.nan

            return SWi, SNWpk, RAIN, SWE, snow_melt

        else:
            rain_frac = np.zeros(ppt.shape)  # initialize the rain fraction array
            # Creates a fraction value based on average temperature that determines
            # if the incoming precipitation is falling as rain, sleet, or snow.
            # if tavg <= 0, make it 0, else if tavg >= 6, make it 1, else (0.167*(tavg-6))
            rain_frac[tavg <= rf_low_thresh_temp] = 0
            rain_frac[tavg >= rf_high_thresh_temp] = 1
            temp_diff_boolean = (tavg < rf_high_thresh_temp) | (tavg > rf_low_thresh_temp)
            rain_frac[temp_diff_boolean] = self.rf_value * (tavg[temp_diff_boolean] - rf_high_thresh_temp)

            RAIN = rain_frac * effppt
            SWE = (1 - rain_frac) * effppt

            # snow melt
            snow_melt = np.zeros(ppt.shape)
            # snow_melt = if melt_rate <= (SWE + yesterday's snowpack), make it melt_rate, else (SWE + yesterday's snowpack)
            snow_melt_boolean = (melt_rate <= (SWE + yest_snwpck))
            snow_melt[snow_melt_boolean] = melt_rate[snow_melt_boolean]
            snow_melt[~snow_melt_boolean] = SWE[~snow_melt_boolean] + yest_snwpck[~snow_melt_boolean]

            SNWpk = np.zeros(ppt.shape)
            # today's snow pack = yesterdays's snow pack + snow water amount - snowmelt
            SNWpk1 = yest_snwpck + SWE - snow_melt
            # set SNWpk1 to 0 if its > 0
            SNWpk[SNWpk1 < 0] = 0
            SNWpk[SNWpk1 >= 0] = SNWpk1[SNWpk1 >= 0]

            # initial soil water balance = yesterday's soil water balance + Rain + snow melt
            SWi = yest_swf + RAIN + snow_melt

            return SWi, SNWpk, RAIN, SWE, snow_melt

    def _surface_runoff(self, SWi, saturation, field_capacity, whc, rf_coeff, geo_dict=None):
        """
        This function determines the runoff part of the model. Runoff is the total of deep drainage and surface runoff.
        :param SWi: initial/starting soil water balance for the day after adding the water amount (rain/snow)
        :param saturation: Soil saturation value (mm)
        :param field_capacity: field capacity value (mm) of soil
        :param whc: Water Holding Capacity (WHC) or available water content (AWC) (mm)
        :param rf_coeff: determines how much of the total runoff is attributed to the surface runoff only
        :param geo_dict: geo-spatial dictionary with attributes of resolution, extent, etc.
        :return: deep drainage and surface runoff
        """

        saturation[saturation < 0] = np.nan
        field_capacity[field_capacity < 0] = np.nan
        whc[whc < 0] = np.nan

        # total runoff based on water left in soil after SAT-FC
        sat_fc = saturation - field_capacity
        Rf1 = SWi - whc
        # if runoff is < 0, make it 0
        Rf = np.zeros(SWi.shape)
        rf_boolean = (Rf1 >= 0)
        Rf[rf_boolean] = Rf1[rf_boolean]

        # Surface runoff
        SRf = np.zeros(SWi.shape)
        # SRf = if rf <= sat_fc, make it (rf * rf_coeff)(35% of the runoff value), else (rf - sat_fc) + (rf_coeff * sat_fc)
        SRf_boolean = (Rf <= sat_fc)
        SRf[SRf_boolean] = Rf[SRf_boolean] * rf_coeff
        SRf[~SRf_boolean] = (Rf[~SRf_boolean] - sat_fc[~SRf_boolean]) + rf_coeff * sat_fc[~SRf_boolean]
        # Deep Drainage
        # DDrain occurs if SWi > WHC, amount of DDrain is SAT <> WHC with a maximum DDrain of SAT - WHC
        DDrain = Rf - SRf

        return DDrain, SRf

    def _veg_et(self, k_factor, ndvi_factor, water_factor, bias_corr, alfa_factor, watermask, pet, ndvi, SWi):
        """
        :param k_factor: 1.25  -> adjusting value in ETa calculation
        :param ndvi_factor: 0.2 -> adjusting value in ETa calculation
        :param water_factor: 0.7 -> VegET over water is determined as 70% of pet
        :param bias_corr: 0.85 -> bias correction for gridmet pet data
        :param alfa_factor: 1.25 -> adjusting grass pet to alfalfa pet
        :param watermask: raster dataset with all inland water bodies
        :param pet: reference ET raster dataset
        :param ndvi: normalized difference vegetation index (ndvi) raster dataset
        :param SWi: initial/starting soil water balance for the day after adding the water amount (rain/snow)
        :param SWf: final/ending soil water balance for the day after taking out ET
        :return:  eta, SWf
        """

        etasw1 = np.zeros(ndvi.shape)
        etasw3 = np.zeros(ndvi.shape)
        etasw4 = np.zeros(ndvi.shape)
        etasw5 = np.zeros(ndvi.shape)
        etasw = np.zeros(ndvi.shape)
        SWf = np.zeros(ndvi.shape)

        etasw1A = (k_factor * ndvi + ndvi_factor) * (pet * bias_corr)
        etasw1B = (k_factor * ndvi) * (pet * bias_corr)

        # etasw1 = if ndvi > 0.4, make it etasw1A, else etasw1B
        ndvi_boolean = (ndvi > 0.4)
        etasw1[ndvi_boolean] = etasw1A[ndvi_boolean]
        etasw1[~ndvi_boolean] = etasw1B[~ndvi_boolean]

        etasw2 = (SWi / (0.5 * self.whc)) * etasw1

        # etasw3 = if SWi > (0.5 * WHC), make it etasw1, else etasw2
        etasw3_boolean = (etasw3 > SWi)
        etasw3[etasw3_boolean] = etasw1[etasw3_boolean]
        etasw3[~etasw3_boolean] = etasw1[~etasw3_boolean]

        # etasw4 = if etasw3 > SWi, make it SWi, else etasw3
        etasw4_boolean = (etasw3 > SWi)
        etasw4[etasw4_boolean] = SWi[etasw4_boolean]
        etasw4[~etasw4_boolean] = etasw3[~etasw4_boolean]

        # etasw = if etasw4 > WHC, make it WHC, else etasw4
        etasw_boolean = (etasw4 > self.whc)
        etasw5[etasw_boolean] = self.whc[etasw_boolean]
        etasw5[~etasw_boolean] = etasw4[~etasw_boolean]

        # ETa of water bodies = 0.70 * (1.25*0.85*ETo)
        water_var = water_factor * bias_corr * alfa_factor
        print(watermask.shape)

        print(pet.shape)
        etawater_boolean = (watermask == 1)
        print(etawater_boolean.shape)
        # put the final etasw values for no-water regions in the final array
        etasw[~etawater_boolean] = etasw5[~etawater_boolean]
        # if it is a water-region, etasw = (calculated ET of water bodies)
        etasw[etawater_boolean] = pet[etawater_boolean] * water_var
        print(etasw.shape)

        SWf1 = SWi - etasw

        # SWf = if SWi > WHC, make it (WHC - etasw), else (if SWf1 < 0.0, make it 0.0, else SWf1)
        SWf_boolean = (SWi > self.whc)
        SWf_boolean2 = (SWf1 < 0.0)

        SWf[SWf_boolean] = self.whc[SWf_boolean] - etasw[SWf_boolean]
        SWf[SWf_boolean2] = 0
        SWf[~SWf_boolean2] = SWf1[~SWf_boolean2]

        return etasw, SWf, etasw5

    def _run_water_bal(self, i, today, interception, whc, field_capacity, saturation,
                       rf_coeff, k_factor, ndvi_factor, water_factor, bias_corr, alfa_factor, watermask, outdir,
                       yest_snwpck=None, yest_swf=None, geoproperties_file=None, daily_mode=True):
        """Here the water balance functions are combined into the water balance model.
        The needed input datasets are collected from buckets in the cloud, the needed functions executed
        and output datasets set up for daily, monthly, yearly rasters.
        """

        #dynamic inputs to the model
        self.ndvi = self.pmanager.get_dynamic_data(today, self.ndvi_settings)
        self.pet = self.pmanager.get_dynamic_data(today, self.pet_settings)
        self.ppt = self.pmanager.get_dynamic_data(today, self.precip_settings)
        self.tavg = self.pmanager.get_dynamic_data(today, self.tavg_settings)
        self.tmin = self.pmanager.get_dynamic_data(today, self.tmin_settings)
        self.tmax = self.pmanager.get_dynamic_data(today, self.tmax_settings)

        # Call Raster Manager function to standardize all the input dataset.
        dynamic_inpts = [self.ndvi, self.pet, self.ppt, self.tavg, self.tmin, self.tmax]

        # All the variables are now Numpy Arrays!
        self.ndvi, self.pet, self.ppt, self.tavg, self.tmin, self.tmax = \
            self.rmanager.normalize_to_std_grid(inputs=dynamic_inpts, resamplemethod='nearest')

        # ====== Call the functions ======
        # output SWi and SNWpk
        SWi, SNWpk, RAIN, SWE, snow_melt = self._soil_water(i, self.ppt, interception, self.tmin, self.tmax, self.tavg,
                                                            self.melt_factor, self.rf_high_thresh_temp, self.rf_low_thresh_temp,
                                                            yest_swf, yest_snwpck)
        DOY, year = self._day_of_year(today=today)

        SWiout =  f'swi_{year}{DOY}.tif'
        print('swout', SWiout)
        SNWpkout = f'snwpk_{year}{DOY}.tif'
        RAINout =  f'rain_{year}{DOY}.tif'
        SWEout = f'swe_{year}{DOY}.tif'
        snow_meltout =  f'snowmelt_{year}{DOY}.tif'

        if daily_mode:
            self.rmanager.output_rasters(SWi, self.outdir, outname=SWiout)
            self.rmanager.output_rasters(SNWpk, self.outdir, outname=SNWpkout)
            self.rmanager.output_rasters(RAIN, self.outdir, outname=RAINout)
            self.rmanager.output_rasters(SWE, self.outdir, outname=SWEout)
            self.rmanager.output_rasters(snow_melt, self.outdir, outname=snow_meltout)

        # output DDRAIN and SRf
        DDrain, SRf = self._surface_runoff(SWi, saturation=self.saturation, field_capacity=self.field_capacity,
                                           whc=self.whc, rf_coeff=self.rf_coeff)
        DDrainout = f'dd_{year}{DOY}.tif'
        SRfout = f'srf_{year}{DOY}.tif'
        if daily_mode:
            self.rmanager.output_rasters(DDrain, self.outdir, outname=DDrainout)
            self.rmanager.output_rasters(SRf, self.outdir, outname=SRfout)

        # output eta and SWf
        etasw, SWf, etasw5 = self._veg_et(k_factor, ndvi_factor, water_factor, bias_corr, alfa_factor, watermask,
                                          self.pet, self.ndvi, SWi)
        etaswout = f'etasw_{year}{DOY}.tif'
        SWfout = f'swf_{year}{DOY}.tif'
        etasw5out = f'etasw5_{year}{DOY}.tif'
        if daily_mode:
            self.rmanager.output_rasters(etasw, outdir, outname=etaswout)
            self.rmanager.output_rasters(SWf, outdir, outname=SWfout)
            self.rmanager.output_rasters(etasw5, outdir, outname=etasw5out)

        return SWf, SNWpk, etasw, DDrain, SRf

    def run_veg_et(self):
        print(
            '''             _ _            ___  ___  _  _ 
            | | | ___  ___ | __>|_ _|| || |
            | ' |/ ._>/ . || _>  | | |_/|_/
            |__/ \___.\_. ||___> |_| <_><_>
                       <___'                '''
        )

        start_dt = datetime.strptime("{}-{:03d}".format(self.start_year, self.start_day), '%Y-%j')
        print(start_dt)
        end_dt = datetime.strptime("{}-{:03d}".format(self.end_year, self.end_day), '%Y-%j')
        print(end_dt)
        time_interval = end_dt - start_dt
        num_days = time_interval.days
        print(num_days)

        accumulate_mode = self.accumulate_mode

        # initially set output_yearly_arrays and output_monhly array to False and you will change
        # them later depending on what is in the accumulate_mode list
        # todo - set these in config.
        output_monthly_arr = False
        output_yearly_arr = False
        # step daily. It is false if not included by default.
        output_daily_arr = False
        output_daily_arr = True

        # Open static inputs and normalize them to standard numpy arrays

        # static inputs
        self.interception = self.pmanager.get_static_data(self.interception_settings)
        self.whc = self.pmanager.get_static_data(self.whc_settings)
        self.field_capacity = self.pmanager.get_static_data(self.field_capacity_settings)
        self.saturation = self.pmanager.get_static_data(self.saturation_settings)
        self.watermask = self.pmanager.get_static_data(self.watermask_settings)
        # package as a list
        static_inputs = [self.interception, self.whc, self.field_capacity, self.saturation, self.watermask]
        # normalizing.
        self.interception, self.whc, self.field_capacity, self.saturation, self.watermask \
            = self.rmanager.normalize_to_std_grid(inputs=static_inputs,resamplemethod='nearest')


        # set monthly and yearly cumulative arrays (use one of the numpys from the
        # static array that has been normalized):
        model_arr_shape = self.interception.shape
        # A total of six output arrays must be instantiated in case accumulate_mode != None
        # monthly
        et_month_cum_arr = np.zeros(model_arr_shape)
        dd_month_cum_arr = np.zeros(model_arr_shape)
        srf_month_cum_arr = np.zeros(model_arr_shape)
        # yearly
        et_yearly_cum_arr = np.zeros(model_arr_shape)
        dd_yearly_cum_arr = np.zeros(model_arr_shape)
        srf_yearly_cum_arr = np.zeros(model_arr_shape)

        # the soil water fraction and snowpack are none to start out.
        changing_swf = None
        changing_snwpck = None
        for i in range(num_days + 1):
            # so what day is it
            today = start_dt + timedelta(days=i)
            if i == 0:

                swf, snwpck, etasw, DDrain, SRf = self._run_water_bal(i, today, self.interception, self.whc, self.field_capacity,
                                                                      self.saturation, self.rf_coeff, self.k_factor,
                                                                      self.ndvi_factor, self.water_factor, self.bias_corr,
                                                                      self.alfa_factor, self.watermask,
                                                                      outdir=self.outdir, yest_snwpck=None, yest_swf=None,
                                                                      geoproperties_file=self.geoproperties_file, daily_mode=output_daily_arr)
                changing_swf = swf
                changing_snwpck = snwpck

            else:

                # see if today is a day that we need to output a monthly raster
                if 'monthly' in accumulate_mode:
                    d = today.day
                    mo = today.month
                    yr = today.year
                    output_monthly_arr = self._end_of_month(d, mo, yr)

                if 'yearly' in accumulate_mode:
                    # todo - deal with Water Year mode later

                    # this function does calendar years
                    d = today.day
                    mo = today.month

                    if d == 31 and mo == 12:
                        output_yearly_arr = True
                else:
                    output_yearly_arr = False

                print('output monthly is {} and output yearly is {}'.format(output_monthly_arr, output_yearly_arr))

                swf, snwpck, etasw, DDrain, SRf = self._run_water_bal(i, today, self.interception, self.whc,
                                                                      self.field_capacity, self.saturation,
                                                                      self.rf_coeff, self.k_factor, self.ndvi_factor,
                                                                      self.water_factor, self.bias_corr, self.alfa_factor,
                                                                      self.watermask, outdir=self.outdir, yest_snwpck=changing_snwpck,
                                                                      yest_swf=changing_swf, geoproperties_file=self.geoproperties_file,
                                                                      daily_mode=output_daily_arr)

                # monthly
                et_month_cum_arr += etasw
                dd_month_cum_arr += DDrain
                srf_month_cum_arr += SRf
                # yearly
                et_yearly_cum_arr += etasw
                dd_yearly_cum_arr += DDrain
                srf_yearly_cum_arr += SRf

                if output_monthly_arr:
                    # function to create monthly output rasters for each variable
                    self.rmanager.output_rasters(et_month_cum_arr, self.outdir,
                                   'model_outputs/etasw_{}{:02d}.tif'.format(today.year, today.month))
                    self.rmanager.output_rasters(dd_month_cum_arr, self.outdir,
                                   'model_outputs/dd_{}{:02d}.tif'.format(today.year, today.month))
                    self.rmanager.output_rasters(srf_month_cum_arr, self.outdir,
                                   'model_outputs/srf_{}{:02d}.tif'.format(today.year, today.month))

                    # zero-out arrays to start the next month over.
                    et_month_cum_arr = np.zeros(model_arr_shape)
                    dd_month_cum_arr = np.zeros(model_arr_shape)
                    srf_month_cum_arr = np.zeros(model_arr_shape)
                    output_monthly_arr = False

                if output_yearly_arr:
                    # function to create yearly output rasters for each variables
                    self.rmanager.output_rasters(et_yearly_cum_arr, self.outdir, 'model_outputs/etasw_{}.tif'.format(today.year))
                    self.rmanager.output_rasters(dd_yearly_cum_arr, self.outdir, 'model_outputs/dd_{}.tif'.format(today.year))
                    self.rmanager.output_rasters(srf_yearly_cum_arr, self.outdir, 'model_outputs/srf_{}.tif'.format(today.year))

                    # zero-out arrays to start the next year over.
                    et_yearly_cum_arr = np.zeros(model_arr_shape)
                    dd_yearly_cum_arr = np.zeros(model_arr_shape)
                    srf_yearly_cum_arr = np.zeros(model_arr_shape)
                    output_yearly_arr = False

                changing_swf = swf
                changing_snwpck = snwpck

            print('-------------------------------')
