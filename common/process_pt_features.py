import pandas as pd
import numpy as np
from datetime import date, timedelta,datetime
from demres.common import codelists,druglists
from demres.common.process_entries import *
from common.helper_functions import *
from demres.demins.constants import Study_Design as sd
from demres.common.logger import logging
from IPython.display import display


def create_pt_features():
    '''
    Creates csv file containing all patients (cases and controls on separate rows)
    with a column for all variables to be analysed
    '''
    pt_features = pd.read_csv('data/raw_data/Extract_Patient_001.txt', usecols=['patid','yob','gender','reggap'], delimiter='\t')

    pt_features = pt_features.loc[pt_features['reggap']==sd.acceptable_number_of_registration_gap_days]
    pt_features.drop('reggap',axis=1,inplace=True)

    pt_features['pracid']=pt_features['patid'].apply(str).str[-3:] #bizarre, but this is how the pracid works!
    pt_features['female'] = pt_features['gender']-1
    pt_features.drop(['gender'],axis=1,inplace=True)
    # pt_features['yob'] = pt_features['yob']+1800 # ditto!
    pt_features['yob'] = pt_features['yob'].astype(str).str[1:]

    return pt_features

def get_index_date_and_caseness_and_add_final_dementia_subtype(all_entries,pt_features):
    '''
    Calculates  index date and establishes caseness by looking for first dementia diagnoses.
    Also looks for final dementia diagnosis (e.g. 'vascular dementia'), as this is likely to be our best guess as to the dementia subtype
    '''
    pegmed = pd.read_csv('dicts/proc_pegasus_medical.csv',delimiter=',')
    pegprod = pd.read_csv('dicts/proc_pegasus_prod.csv',delimiter=',')
    medcodes = get_medcodes_from_readcodes(codelists.alzheimer_vascular_and_non_specific_dementias['codes'])
    prodcodes = get_prodcodes_from_drug_name(codelists.alzheimer_vascular_and_non_specific_dementias['medications'])


    entries_with_antidementia_presc_mask = all_entries['prodcode'].isin(prodcodes)
    entries_with_dementia_dx_mask = all_entries['medcode'].isin(medcodes)

    #For the purpose of my paper's flow chart of patient selection,
    #get number of cases where there is an antidementia prescription but not a dementia diagnosis
    patids_prescribed_antidementia_drugs = set(all_entries.loc[entries_with_antidementia_presc_mask,'patid'])
    patids_with_dementia_dx = set(all_entries.loc[entries_with_dementia_dx_mask,'patid'])
    total_pts_prescribed_antidementia_drugs_but_no_dementia_dx = len(pt_features[(pt_features['patid'].isin(patids_prescribed_antidementia_drugs))&~(pt_features['patid'].isin(patids_with_dementia_dx))])
    print('Number of patients prescribed antidementia drugs but not diagnosed with dementia:',total_pts_prescribed_antidementia_drugs_but_no_dementia_dx)

    # from the all_entries df, get just those which contain a dementia dx or an antidementia drug prescription
    all_dementia_entries = all_entries[entries_with_antidementia_presc_mask|entries_with_dementia_dx_mask]
    # for clarity, look up the Read terms
    all_dem_labelled = pd.merge(all_dementia_entries,pegmed,how='left')[['patid','prodcode','medcode','sysdate','eventdate','type']]
    # for clarity, look up the drug names
    all_dem_labelled = pd.merge(all_dem_labelled,pegprod,how='left')[['patid','medcode','prodcode','sysdate','eventdate','type','drugsubstance']]
    all_dem_labelled.loc[:,'eventdate']=pd.to_datetime(all_dem_labelled.loc[:,'eventdate'])
    #Get the date of earliest dementia diagnosis / antidementia drug prescription - this will be the revised index date, and will also determine revised caseness
    earliest_dementia_dates = all_dem_labelled.groupby('patid')['eventdate'].min().reset_index()
    earliest_dementia_dates.rename(columns={'eventdate':'index_date'},inplace=True)

    pt_features = pd.merge(pt_features,earliest_dementia_dates,how='left')
    pt_features['isCase']=np.where(pd.notnull(pt_features['index_date']),True,False)
    # Get the final dementia diagnosis
    just_dementia_diagnoses = all_dem_labelled[pd.isnull(all_dem_labelled['prodcode'])]
    final_dementia_dx = just_dementia_diagnoses.loc[just_dementia_diagnoses.groupby('patid')['eventdate'].idxmax()][['patid','medcode']]
    final_dementia_dx.rename(columns={'medcode':'final dementia medcode'},inplace=True)


    pt_features = pd.merge(pt_features,final_dementia_dx,how='left')
    return pt_features

def avoid_specific_dementia_subtypes(pt_features):
    print('removing cases where final dementia subtype is a specific, non-Alzheimer, non-VaD dementia')
    previous_case_count = len(pt_features[pt_features['isCase']==True])
    pt_features = pt_features[(pt_features['isCase']==False) |~(pt_features['final dementia medcode'].isin(get_medcodes_from_readcodes(codelists.specific_dementias['codes'])))]
    new_case_count = len(pt_features[pt_features['isCase']==True])
    print('Number of cases removed: ', previous_case_count-new_case_count)
    print('Number of patients (cases and controls)',len(pt_features))
    return pt_features

def add_data_start_and_end_dates(all_encounters,pt_features):
    '''
    This function looks at all clinical encounters (e.g. referrals, consultations, but not prescriptions)
    to find the data start and end dates.
    '''
    logging.debug('add_sys_start_and_end_dates_to_pt_features all_entries.csv')

    #Calculate the data_end date - we can use the last sysdate
    print('calculating latest_sysdate')
    latest_sysdates = all_encounters.groupby('patid')['sysdate'].max().reset_index()
    latest_sysdates.rename(columns={'sysdate':'data_end'},inplace=True)
    pt_features = pd.merge(pt_features,latest_sysdates,how='left')

    #We now find the earliest sysdate - however, this will not necessarily be the data_start date, as often patients have detailed notes prior to this, entered retrospectively
    print('calculating earliest_sysdate')
    earliest_sysdates = all_encounters.groupby('patid')['sysdate'].min().reset_index()
    earliest_sysdates.rename(columns={'sysdate':'earliest_sysdate'},inplace=True)
    pt_features = pd.merge(pt_features,earliest_sysdates,how='left')

    #As an alternative to the earliest sysdate, find the earliest two year period in which you have at least 40
    # eventdates (not sysdates) - this, in my opinion, is likely to be when the electronic record
    # started to be filled in prospectively (the reason for the discrepancy between the eventdate and the sysdate
    # is probably because the entries were given a new sysdate for some reason, e.g. software update)
    print('resampling all_encounters - may take some time...')
    resampled_entries = all_encounters.set_index('eventdate').groupby('patid').resample('24M').size()
    resampled_entries2 = resampled_entries.reset_index()
    resampled_entries2.columns = ['patid','twentyfour_month_period_ending','consultation_count']
    resampled_entries3 = resampled_entries2.loc[resampled_entries2['consultation_count']>=40]
    resampled_entries4 = resampled_entries3.groupby('patid').twentyfour_month_period_ending.min().reset_index()
    resampled_entries4.columns = ['patid','estimated_data_start'] #conservative estimate, as the estimated data start will be at the END of the 24 month period of high activity
    pt_features = pd.merge(pt_features,resampled_entries4,how='left')

    # Watch out for 'converted codes' (medcode 14) - these are uninformative medcodes where the specific Read codes have
    # been lost, probably due to some software update in the 1990s.
    print('locating converted codes')
    converted_code_entries = all_encounters[all_encounters['medcode']==14]
    latest_converted_code_entries = converted_code_entries.groupby('patid')['sysdate'].max().reset_index()
    latest_converted_code_entries.columns = ['patid','sysdate_of_final_converted_code']
    pt_features = pd.merge(pt_features,latest_converted_code_entries,how='left')

    # Now choose which measure we are going to use for data_start. Note that if a converted code exists for a patid,
    # it's probably safest just to use the earliest sysdate
    print('choosing most appropriate measure of data_start')
    dont_use_earliest_sysdate_mask = ((pt_features['estimated_data_start']<pt_features['earliest_sysdate']) &
        ((pt_features['estimated_data_start'] > pt_features['sysdate_of_final_converted_code']) | (pd.isnull(pt_features['sysdate_of_final_converted_code'])))
            )
    pt_features['data_start']=np.nan
    pt_features.loc[dont_use_earliest_sysdate_mask,'data_start']=pt_features['estimated_data_start'].copy()
    pt_features.loc[~dont_use_earliest_sysdate_mask,'data_start']=pt_features['earliest_sysdate'].copy()
    pt_features['data_start'] = pd.to_datetime(pt_features['data_start'])

    # Remove patients without any events
    print('removing patients without any events')
    no_event_mask = pd.isnull(pt_features['earliest_sysdate'])
    print('There are {0} patients without any events'.format(len(pt_features[no_event_mask])))

    pt_features = pt_features.loc[~no_event_mask].copy()

    pt_features.drop(['earliest_sysdate','sysdate_of_final_converted_code','estimated_data_start'],inplace=True,axis=1)


    pt_features.to_csv('data/processed_data/pt_features_demins.csv',index=False)

    return pt_features


def match_cases_and_controls(pt_features,window):
    '''
    Matches cases to controls.
    Controls are given an index date only after being matched.
    '''
    req_yrs_post_index=sd.req_yrs_post_index
    start_year=abs(window['start_year'])
    pt_features['matchid']=np.nan

    pt_features.loc[:,'total_available_data']= pt_features.loc[:,'data_end'] - pt_features.loc[:,'data_start']
    pt_features.sort_values(inplace=True,by='total_available_data',ascending=True) # To make matching more efficient, first try to match to controls the cases with with the LEAST amount of available data

    enough_data_mask = pt_features['data_start'] <= (pt_features['index_date'] - timedelta(days=(365*start_year)))
    cases_with_enough_data = pt_features.loc[(pt_features['isCase']==True) & enough_data_mask].copy()
    cases_without_enough_data = pt_features.loc[(pt_features['isCase']==True) & ~enough_data_mask].copy()

    print('All cases',len(pt_features[pt_features['isCase']==True]))
    print('Number of cases with 10 years of data',len(cases_with_enough_data))

    #The following information is for my paper's patient study flow chart only
    print('Number of cases without 10 years of data (to be discarded):',len(cases_without_enough_data))

    controls = pt_features.loc[pt_features['isCase']==False].copy()
    print('Number of controls',len(controls))

    for index,row in cases_with_enough_data.iterrows():
        if pd.isnull(row['matchid']):
            patid = row['patid']
            yob = row['yob']
            female = row['female']
            index_date = row['index_date']
            # Define matching criteria
            matches_yob = controls['yob']==yob
            matches_gender = controls['female']==female
            # matches_practice = controls['pracid']==pracid
            enough_data_after_index_date = controls['data_end'] >= (index_date + timedelta(days=(365*req_yrs_post_index)))
            enough_data_before_index_date = controls['data_start'] <= (index_date - timedelta(days=(365*start_year)))
            match_mask =  matches_yob & matches_gender & enough_data_after_index_date & enough_data_before_index_date #& matches_practice
            if len(controls[match_mask])>0:
                best_match_index = controls.loc[match_mask,'total_available_data'].idxmin(axis=1) # To make matching more efficient, first try to match cases with those controls with the LEAST amount of available data
                best_match_id = controls.ix[best_match_index]['patid']
                #give both the case and control a unique match ID (for convenience, I've used the iterrows index)
                pt_features.loc[index,'matchid']=index
                pt_features.loc[best_match_index,'matchid']=index
                pt_features.loc[best_match_index,'index_date']=index_date
                controls = controls.drop(best_match_index) #drop this row from controls dataframe so it cannot be matched again

    pt_features.drop('total_available_data',axis=1,inplace=True)

    #Remove patients without a matchid
    to_remove_mask = pd.isnull(pt_features['matchid'])
    print(len(pt_features[to_remove_mask & (pt_features['isCase']==True)]),' cases being removed as unmatchable')
    print(len(pt_features[to_remove_mask & (pt_features['isCase']==False)]),' controls being removed as unmatchable')
    print(len(pt_features[to_remove_mask]),' total patients being removed as unmatchable')
    # pt_features[to_remove_mask].to_csv('data/pt_data/removed_patients/removed_unmatched_patients.csv',index=False)
    pt_features = pt_features.loc[~to_remove_mask].copy()

    #Now that we have an index date for both cases and controls, finally calculate age at index date
    pt_features.loc[:,'age_at_index_date'] = pd.DatetimeIndex(pt_features['index_date']).year.astype(int) - (1900 + pt_features['yob'].astype(int))

    pt_features.loc[:,'matchid']=pt_features['matchid'].astype(int)
    return pt_features

def get_multiple_condition_statuses(pt_features,entries,prescriptions,window,conditions):
    for condition in conditions:
        print(condition['name'])
        pt_features = get_condition_status(pt_features,entries,prescriptions,window,condition)
    return pt_features

def get_condition_status(pt_features,entries,prescriptions,window,condition):
    '''
    Searches a patient's history (i.e. the list of medcoded entries) for any one of a list of related Read codes
    (e.g. 'clinically significant alcohol use', or 'insomnia') during a given exposure window  (e.g. 5-10 years prior to index date).
    According to the 'count_or_boolean' parameter, will return either a count of the Read codes (i.e. insomnia) or a simple boolean (all other conditions).
    '''

    new_colname = condition['name']

    if new_colname in pt_features.columns: #delete column if it already exists (otherwise this causes problems with the 'fillna' command below)
        pt_features.drop(new_colname,axis=1,inplace=True)

    # If we're using all the patient's history from the exposure window back to birth
    #(e.g. for intellectual disability), overwrite the predefined exposure windows with a single window
    if condition['record_exposure_in_window_period_only']==True:
        start_year = timedelta(days=(365*abs(window['start_year'])))
    else: #for all other conditions, record exposure from end of window period back to start of their records
        start_year = timedelta(days=(365*100))

    medcount_colname = new_colname + '_Read_code_count'

    medcodes = get_medcodes_from_readcodes(condition['codes'])
    medcode_events = entries[entries['medcode'].isin(medcodes)]

    medcode_events = medcode_events[pd.notnull(medcode_events['eventdate'])] #drops a small number of rows  with NaN eventdates
    # display(medcode_events.head(10))

    # print('\tTotal {0} events in all medcoded_events dataframe: {1}'.format(condition['name'],len(medcode_events)))
    medcode_events = pd.merge(medcode_events[['patid','eventdate']],pt_features[['patid','index_date']],how='inner',on='patid')

    # Restrict event counts to those that occur during pt's exposure window
    relevant_event_mask = (medcode_events['eventdate']>=(medcode_events['index_date']-start_year)) & (medcode_events['eventdate']<=(medcode_events['index_date']-timedelta(days=(365*sd.window_length_in_years))))
    window_medcode_events = medcode_events.loc[relevant_event_mask]
    window_medcode_events = window_medcode_events.groupby('patid')['eventdate'].count().reset_index()
    window_medcode_events.columns=['patid',medcount_colname]
    # print('\t{0} events in this window for our patients: {1}'.format(new_colname,len(window_medcode_events)))

    #delete zero counts
    window_medcode_events = window_medcode_events.loc[window_medcode_events[medcount_colname]>0]

    pt_features = pd.merge(pt_features,window_medcode_events,how='left')
    pt_features[medcount_colname].fillna(0,inplace=True)


    pt_features.loc[pt_features[medcount_colname]>0,new_colname] = 1
    pt_features.loc[pt_features[medcount_colname]==0,new_colname] = 0

    if len(condition['medications'])>0:
        presc_count_colname = new_colname + '_prescription_count'

        prodcodes = get_prodcodes_from_drug_name(condition['medications'])
        prescriptions = prescriptions.loc[prescriptions['prodcode'].isin(prodcodes)].copy()
        prescriptions = prescriptions.loc[pd.notnull(prescriptions['qty'])].copy() #remove the relatively small number of prescriptions where the quantity is NaN

        # Some conditions (e.g. insomnia) are also defined by whether or not certain medications are prescribed
        prescriptions = pd.merge(prescriptions[['patid','eventdate']],pt_features[['patid','index_date']],how='inner',on='patid')

        start_year = timedelta(days=(365*abs(window['start_year'])))
        end_year = timedelta(days=(365*abs(window['start_year']+sd.window_length_in_years)))
        timely_presc_mask = (prescriptions['eventdate']>=(prescriptions['index_date']-start_year)) & (prescriptions['eventdate']<=(prescriptions['index_date']-end_year))
        prescriptions = prescriptions.loc[timely_presc_mask].copy()


        prescriptions = prescriptions.groupby('patid')['eventdate'].count().reset_index()
        prescriptions.columns=['patid',presc_count_colname]
        prescriptions = prescriptions.loc[prescriptions[presc_count_colname]>0]

        pt_features = pd.merge(pt_features,prescriptions,how='left')
        pt_features[presc_count_colname].fillna(0,inplace=True)

        # convert condition from a count to a boolean
        pt_features.loc[(pt_features[medcount_colname]>0) | (pt_features[presc_count_colname]>0),new_colname] = 1
        pt_features.drop(presc_count_colname,axis=1,inplace=True)

    pt_features.drop(medcount_colname,axis=1,inplace=True)

    pt_features[new_colname] = pt_features[new_colname].astype(int)

    return pt_features

def get_relevant_and_reformatted_prescs(prescriptions,druglists,pt_features,window):
    '''
    Filter prescriptions to only include ones which are for relevant drugs and within the exposure window,
    and create 'amount' and 'unit' columns (necessary for calculating PDD)
    '''
    prescs = pd.merge(prescriptions,pt_features[['patid','index_date']],how='left',on='patid')
    prescs = prescs.loc[pd.notnull(prescs['qty'])].copy() #remove the relatively small number of prescriptions where the quantity is NaN

    pegprod = pd.read_csv('dicts/proc_pegasus_prod.csv')
    prescs = pd.merge(prescs,pegprod[['prodcode','strength','route','drugsubstance']],how='left')

    #Only use prescriptions belonging to the main exposure window (not the ones used in sensitivity analysis)
    start_year = timedelta(days=(365*abs(sd.exposure_windows[1]['start_year'])))
    end_year = timedelta(days=(365*abs(sd.exposure_windows[1]['start_year']+sd.window_length_in_years)))
    timely_presc_mask = (prescs['eventdate']>=(prescs['index_date']-start_year)) & (prescs['eventdate']<=(prescs['index_date']-end_year))
    timely_prescs = prescs.loc[timely_presc_mask].copy()

    all_drugs = [drug for druglist in druglists for drug in druglist['drugs'] ]

    prodcodes = get_prodcodes_from_drug_name(all_drugs)
    relev_prescs = timely_prescs.loc[timely_prescs['prodcode'].isin(prodcodes)].copy()

    # Create new columns ('amount' and 'unit', extracted from the 'substrance strength' string)
    amount_and_unit = relev_prescs['strength'].str.extract('([\d\.]+)([\d\.\+ \w\/]*)',expand=True)
    amount_and_unit.columns=['amount','unit']
    amount_and_unit.amount = amount_and_unit.amount.astype('float')
    reformatted_prescs = pd.concat([relev_prescs,amount_and_unit],axis=1).drop(['numpacks','numdays','packtype','issueseq'],axis=1)

    # Convert micrograms to mg
    micro_mask = reformatted_prescs['unit'].str.contains('microgram',na=False,case=False)
    reformatted_prescs.loc[micro_mask,'amount'] /= 1000
    reformatted_prescs.loc[micro_mask,'unit'] = 'mg'

    #Convert mg/Xml to mg for simplicity
    micro_mask = reformatted_prescs['unit'].str.contains('mg/',na=False,case=False)
    reformatted_prescs.loc[micro_mask,'unit'] = 'mg'

    #Remove the small number of  prescriptions where there is no amount
    reformatted_prescs = reformatted_prescs[pd.notnull(reformatted_prescs['amount'])].copy()

    # Create a 'total_amount' column - used to calculate each pt's PDDs for a given drug.
    reformatted_prescs['total_amount'] = reformatted_prescs['qty']*reformatted_prescs['amount']

    #Change all 'numeric daily doses' (NDD) from 0 (this appears to be the default in the CPRD data) to 1.
    #Note that an NDD of 2 means 'twice daily'
    reformatted_prescs.loc[reformatted_prescs['ndd'] == 0,'ndd']=1

    return reformatted_prescs

def create_pdd_for_each_drug(prescriptions,pt_features,window):
    '''
    Create a prescribed daily dose for each drug, based on average doses in the patient sample during the main exposure window
    '''

    prescs = get_relevant_and_reformatted_prescs(prescriptions,all_drugs,pt_features,window)

    pdds = pd.DataFrame(columns=['drug_name','pdd(mg)'])


    prescs = prescs.loc[prescs['drugsubstance'].str.upper().isin(all_drugs)]

    #Calculate the prescribed daily dose (PDD) for each drug
    for drug in all_drugs:
        drug = drug.upper()
        temp_prescs = prescs[prescs['drugsubstance'].str.upper()==drug].copy()
        if(len(temp_prescs))>0:
            drug_amounts = np.array(temp_prescs['amount'])*np.array(temp_prescs['ndd'])
            drug_weights = np.array(temp_prescs['qty'])/np.array(temp_prescs['ndd'])
            pdd = np.average(drug_amounts,weights=drug_weights)
            print(drug,'\tpdd:',str(pdd))
            pdds.loc[len(pdds)]=[drug,pdd]
            assert pd.notnull(pdd)
        else:
            print(drug,'\tNo prescriptions found')

    #Write PDDs to file for reference
    pdds.to_csv('output/drug_pdds.csv',index=False)


def create_PDD_columns_for_each_pt(pt_features,window,druglists,prescriptions):
    '''
    Adds a prescribed daily doses (PDD) column for each drug in a druglist to the pt_features dataframe
    '''
    pdds = pd.read_csv('output/drug_pdds.csv', delimiter=',')
    prescs = get_relevant_and_reformatted_prescs(prescriptions,druglists,pt_features,window)
    prescs['drugsubstance'] = prescs['drugsubstance'].str.upper()
    prescs_grouped = prescs.groupby(by=['patid','drugsubstance']).total_amount.sum().reset_index()
    for druglist in druglists:
        print(druglist['name'])
        capitalised_drugs = [drug.upper() for drug in druglist['drugs']]
        new_colname = druglist['name']+'_100_pdds'
        # prodcodes = get_prodcodes_from_drug_name(druglist['drugs'])
        relev_prescs = prescs_grouped.loc[prescs_grouped['drugsubstance'].isin(capitalised_drugs)]
        print('There are {0} relevant prescription entries for {1}'.format(len(relev_prescs),druglist['name']))

        # Sum the total pdds of a particular drug type for each patients
        # (e.g. lorazepam AND zopiclone AND diazepam when calculating benzo/z-drug pdds).
        # Then divide by 100, because 100_PDDs is an easier-to-interpret unit for odds ratio than PDDs alone

        # relev_prescs['drugsubstance'] =  relev_prescs['drugsubstance'].str.upper()

        relev_prescs = pd.merge(relev_prescs,pdds,left_on='drugsubstance',right_on='drug_name',how='left')[['patid','drugsubstance','total_amount','pdd(mg)']]
        relev_prescs[new_colname] = (relev_prescs['total_amount'] / relev_prescs['pdd(mg)'])/100
        pt_pdds = relev_prescs.groupby(by='patid')[new_colname].sum().reset_index().copy()
        if new_colname in pt_features.columns: #delete column if it already exists (otherwise this causes problems with the 'fillna' command below)
            pt_features.drop(new_colname,axis=1,inplace=True)
        pt_features = pd.merge(pt_features,pt_pdds,how='left')
        pt_features[new_colname].fillna(value=0,inplace=True)
    return pt_features



def create_quantiles_and_booleans(pt_features):
    '''
    Converts various continuous variables (e.g. age, insomnia) into quantiles,
    and converts others (insomnia, benzodiazepine_pdd) into booleans
    '''

    # Create quantiles for age
    # (these are only used in the baseline characteristics section of the paper, not in the actual logistic regression)
    age_65_69_mask = pt_features['age_at_index_date']<70
    age_70_74_mask = (pt_features['age_at_index_date']<75) & (pt_features['age_at_index_date']>=70)
    age_75_79_mask = (pt_features['age_at_index_date']<80) & (pt_features['age_at_index_date']>=75)
    age_80_84_mask = (pt_features['age_at_index_date']<85) & (pt_features['age_at_index_date']>=80)
    age_85_89_mask = (pt_features['age_at_index_date']<90) & (pt_features['age_at_index_date']>=85)
    age_90_94_mask = (pt_features['age_at_index_date']<95) & (pt_features['age_at_index_date']>=90)
    age_95_99_mask = (pt_features['age_at_index_date']<100) & (pt_features['age_at_index_date']>=95)
    above_99_mask = pt_features['age_at_index_date']>=100
    pt_features.loc[age_65_69_mask,'age_at_index_date:65-69']=1
    pt_features.loc[~age_65_69_mask,'age_at_index_date:65-69']=0
    pt_features.loc[age_70_74_mask,'age_at_index_date:70-74']=1
    pt_features.loc[~age_70_74_mask,'age_at_index_date:70-74']=0
    pt_features.loc[age_75_79_mask,'age_at_index_date:75-79']=1
    pt_features.loc[~age_75_79_mask,'age_at_index_date:75-79']=0
    pt_features.loc[age_80_84_mask,'age_at_index_date:80-84']=1
    pt_features.loc[~age_80_84_mask,'age_at_index_date:80-84']=0
    pt_features.loc[age_85_89_mask,'age_at_index_date:85-89']=1
    pt_features.loc[~age_85_89_mask,'age_at_index_date:85-89']=0
    pt_features.loc[age_90_94_mask,'age_at_index_date:90-99']=1
    pt_features.loc[~age_90_94_mask,'age_at_index_date:90-99']=0
    pt_features.loc[above_99_mask,'age_at_index_date:above_99']=1
    pt_features.loc[~above_99_mask,'age_at_index_date:above_99']=0

    for drug in ['hypnotics_100_pdds']:
        drug_pdds = pt_features[drug] * 100 #convert unit from '100 pdds' to 'pdds'
        drug_0_mask = drug_pdds==0
        drug_1_10_mask = (drug_pdds>0) & (drug_pdds<=10)
        drug_11_100_mask = (drug_pdds>10) & (drug_pdds<=100)
        drug_101_1000_mask = (drug_pdds>100) & (drug_pdds<=1000)
        drug_1001_10000_mask = (drug_pdds>1000) & (drug_pdds<=10000)
        drug_above_10000_mask = drug_pdds>10000
        drug_name_with_100_pdds_removed = drug.replace('s_100','')

        pt_features.loc[drug_0_mask,drug_name_with_100_pdds_removed+':00000']=1
        pt_features.loc[~drug_0_mask,drug_name_with_100_pdds_removed+':00000']=0

        pt_features.loc[drug_1_10_mask,drug_name_with_100_pdds_removed+':00001_10']=1
        pt_features.loc[~drug_1_10_mask,drug_name_with_100_pdds_removed+':00001_10']=0

        pt_features.loc[drug_11_100_mask,drug_name_with_100_pdds_removed+':00011_100']=1
        pt_features.loc[~drug_11_100_mask,drug_name_with_100_pdds_removed+':00011_100']=0

        pt_features.loc[drug_101_1000_mask,drug_name_with_100_pdds_removed+':00101_1000']=1
        pt_features.loc[~drug_101_1000_mask,drug_name_with_100_pdds_removed+':00101_1000']=0

        pt_features.loc[drug_1001_10000_mask,drug_name_with_100_pdds_removed+':01001_10000']=1
        pt_features.loc[~drug_1001_10000_mask,drug_name_with_100_pdds_removed+':01001_10000']=0

        pt_features.loc[drug_above_10000_mask,drug_name_with_100_pdds_removed+':10000_and_above']=1
        pt_features.loc[~drug_above_10000_mask,drug_name_with_100_pdds_removed+':10000_and_above']=0

    return pt_features
