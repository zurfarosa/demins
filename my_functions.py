import pandas as pd
import numpy as np
import csv
from datetime import date, timedelta
from constants import Entry_Type, Study_Design

def create_pegmed():
    """
    Creates a cleaned up version of Pegasus Medical dictionary in csv form
    """
    raw_pegmed = pd.read_csv('data/dicts/raw_pegasus_medical.txt',delimiter='\t',skiprows=[0,1,2],header=None)
    raw_pegmed.columns=['medcode','readcode','clinical events','immunisation events','referral events','test events','read term','database build']
    raw_pegmed.to_csv('data/dicts/proc_pegasus_medical.csv',index=False)

def create_pegprod():
    """
    Creates a cleaned up version of Pegasus Products dictionary in csv form
    """
    raw_pegprod = pd.read_csv('data/dicts/raw_pegasus_product.txt',delimiter='\t',encoding='latin-1', skiprows=[0,1],header=None)
    raw_pegprod.columns=['product code','XXX code','therapy events','product name','drug substance name','substance strength','formulation','route','BNF code','BNF header','database build','unknown column']
    raw_pegprod.to_csv('data/dicts/proc_pegasus_prod.csv',index=False)

def create_medcoded_entries():
    """
    Creates create_medcoded_entries.csv
    This is a file containing a dataframe containing simplified data
    (just patient ID, eventdate, sysdate, and medcode) from the
    Extract_Clinical_001 and 002 files, Extract_Test_001 and 002 file and Extract_Referral_001 file
    (but not the Extract_Therapy_001 or 002 files or Extract_Consultations_001 or 002)
    """
    clin1 = pd.read_csv('data/pt_data/Extract_Clinical_001.txt',delimiter='\t')
    clin2 = pd.read_csv('data/pt_data/Extract_Clinical_002.txt',delimiter='\t')
    clinical = pd.concat([clin1,clin2])[['patid','sysdate','eventdate','medcode']]
    clinical['eventdate'] = pd.to_datetime(clinical['eventdate'])
    clinical['sysdate'] = pd.to_datetime(clinical['sysdate'])
    clinical['type']=Entry_Type.clinical
    test1 = pd.read_csv('data/pt_data/Extract_Test_001.txt',delimiter='\t')
    test2 = pd.read_csv('data/pt_data/Extract_Test_002.txt',delimiter='\t')
    test = pd.concat([test1,test2])[['patid','sysdate','eventdate','medcode']]
    test['eventdate'] = pd.to_datetime(test['eventdate'])
    test['sysdate'] = pd.to_datetime(test['sysdate'])
    test['type']=Entry_Type.test

    referral = pd.read_csv('data/pt_data/Extract_Referral_001.txt',delimiter='\t')
    referral = referral[['patid','sysdate','eventdate','medcode']]
    referral['eventdate'] = pd.to_datetime(referral['eventdate'])
    referral['sysdate'] = pd.to_datetime(referral['sysdate'])
    referral['type']=Entry_Type.referral

    medcoded_entries = pd.concat([clinical,test,referral])
    medcoded_entries.to_csv('data/pt_data/medcoded_entries.csv',index=False)

def create_consultations():
    """
    Creates a csv file containing all the data from Extract_Consultation_001.txt and Extract_Consultation_002.txt
    """
    cons1 = pd.read_csv('data/pt_data/Extract_Consultation_001.txt',delimiter='\t')
    cons2 = pd.read_csv('data/pt_data/Extract_Consultation_002.txt',delimiter='\t')
    consultations = pd.concat([cons1,cons2])[['patid','sysdate','eventdate']]
    consultations['eventdate'] = pd.to_datetime(consultations['eventdate'])
    consultations['sysdate'] = pd.to_datetime(consultations['sysdate'])
    consultations['type']= Entry_Type.consultation
    consultations.to_csv('data/pt_data/consultations.csv',index=False)

def create_all_entries():
    """
    Creates a csv file (all_entries.csv) containing all entries (consultations, plus the medcoded entries - clinicals, tests, referrals)
    The csv file is only used as  a way of estimating the dates of data extraction (hopefully CPRD will tell me how to do this properly soon)
    """
    consultations = pd.read_csv('data/pt_data/consultations.csv',delimiter=',')
    medcoded_entries = pd.read_csv('data/pt_data/medcoded_entries.csv',delimiter=',')
    all_entries = pd.concat([consultations,medcoded_entries])
    all_entries.to_csv('data/pt_data/all_entries.csv',index=False)

def clean_matching():
    """
    Removes the 196 rows from the 'matching' dataframe where there is no control matching the case,
    then creates a files called 'unmatched_cases' for the lone cases, and a file called
    'matching_unmatched_removed.csv' for the cleaned up matched pairs
    """
    matching = pd.read_csv('data/pt_data/Matching_File.txt',delimiter='\t')
    matching_unmatched_removed = matching[matching['control_pracid']!='.']
    matching_unmatched_removed.to_csv('data/pt_data/matching_unmatched_removed.csv',index=False)
    unmatched_cases = matching[matching['control_patid']=='.'][['case_patid','case_pracid','case_gender','case_birthyear','case_index']]
    unmatched_cases.columns=['patid','pracid','gender','birthyear','index_date']
    unmatched_cases['isCase']=True
    unmatched_cases.to_csv('data/pt_data/ummatched_cases.csv',index=False)

def create_pt_features():
    '''
    Creates csv file containing all patients (cases and controls on separate
    rows) with a column for all variables for logistic regression
    '''

    matching = pd.read_csv('data/pt_data/matching_unmatched_removed.csv',delimiter=',')
    del(matching['match'])
    del(matching['control_end'])
    del(matching['control_start'])

    #Create the cases
    feature1 = matching.copy(deep=True)
    # reorder the columns
    feature1=feature1[['case_patid','case_pracid','case_gender','case_birthyear','case_index']]
    feature1['isCase']=True
    # rename the columns
    feature1.columns=['patid','pracid','gender','birthyear','index_date','isCase']

    #Create the controls
    feature2 = matching.copy(deep=True)
    # reorder the columns
    feature2=feature2[['control_patid','control_pracid','control_gender','control_birthyear','case_index']]
    feature2['isCase']=False
    # rename the columns
    feature2.columns=['patid','pracid','gender','birthyear','index_date','isCase']
    feature2['index_date']=np.nan

    #Merge cases and controls
    features = pd.concat([feature1,feature2])
    features=features[['patid','pracid','gender','birthyear','index_date','isCase']]

    # Add the previously removed patients from ummatched_cases.csv (these were unmatched in the original raw data files)
    ummatched_cases = pd.read_csv('data/pt_data/ummatched_cases.csv',delimiter=',',parse_dates=['index_date'])
    features = pd.concat([features,ummatched_cases])

    # features['index_date']=pd.to_datetime(features['index_date'])

    features.to_csv('data/pt_data/pt_features.csv',index=False)

def add_sys_start_and_end_dates_to_pt_features():
    '''
    Needs the dateframe created by create_medcoded_entries() to be passed to it.
    This will need to be rewritten when I know the PROPER way to get the start and end dates for each patient's period of data extraction.
    As it stands, this function looks at all the medcoded_entries, and looks for the first and last 'sysdated' entry.
    '''

    all_entries = pd.read_csv('data/pt_data/all_entries.csv',delimiter=',',parse_dates=['sysdate','eventdate'])

    earliest_sysdates = all_entries.sort_values(by='sysdate').groupby('patid').first().reset_index().loc[:,['patid','sysdate']]
    earliest_sysdates = earliest_sysdates.loc[:,['patid','sysdate']]
    earliest_sysdates.columns = ['patid','earliest_sysdate']

    latest_sysdates = all_entries.sort_values(by='sysdate',ascending=False).groupby('patid').first().reset_index().loc[:,['patid','sysdate']]
    latest_sysdates = latest_sysdates.loc[:,['patid','sysdate']]
    latest_sysdates.columns = ['patid','latest_sysdate']

    pt_features = pd.read_csv('data/pt_data/pt_features.csv',delimiter=',',parse_dates=['index_date'])
    pt_features = pd.merge(pt_features,earliest_sysdates,how='left')
    pt_features = pd.merge(pt_features,latest_sysdates,how='left')

    # Remove pts without any sysdates - this also seems to remove the unmatched cases from the clean_matching function above
    pt_features = pt_features[pd.notnull(pt_features['earliest_sysdate'])]

    pt_features.to_csv('data/pt_data/pt_features.csv',index=False)

def add_length_of_data_pre_and_post_indexdate_to_pt_features(cases_or_controls='both'):
    pt_features = pd.read_csv('data/pt_data/pt_features.csv',delimiter=',', parse_dates=['index_date','earliest_sysdate','latest_sysdate'])

    row_index = pd.notnull(pt_features['earliest_sysdate']) & pd.notnull(pt_features['latest_sysdate'])
    if cases_or_controls=='cases':
         row_index = row_index & pt_features['isCase']==True
         # Until they've been rematched, there's no point calculating the pre and post index data length for the controls, as they don't yet have an index_date!
    elif cases_or_controls=='controls':
         row_index = row_index & pt_features['isCase']==False

    pt_features.loc[row_index,'length_of_data_pre_index_date'] = ((pt_features['index_date']-pt_features['earliest_sysdate'])/np.timedelta64(1, 'D'))
    pt_features.loc[row_index,'length_of_data_post_index_date'] = ((pt_features['latest_sysdate']-pt_features['index_date'])/np.timedelta64(1, 'D'))

    pt_features.to_csv('data/pt_data/pt_features.csv',index=False)


def delete_patients_if_not_enough_data(cases_or_controls='both'):
    pt_features = pd.read_csv('data/pt_data/pt_features.csv',delimiter=',')

    row_index = (pt_features['length_of_data_pre_index_date']<(Study_Design.total_years_required_pre_index_date*365)) \
            | (pt_features['isCase']==False & (pt_features['length_of_data_post_index_date']<(Study_Design.years_of_data_after_index_date_required_by_controls*365)))
    if cases_or_controls=='cases':
         row_index = row_index & pt_features['isCase']==True
    elif cases_or_controls=='controls':
         row_index = row_index & pt_features['isCase']==False

    #delete cases and controls if not enough data prior to index dates
    pd.options.mode.chained_assignment = None  # default='warn'
    removed_pts = pt_features.loc[row_index]
    removed_pts['reason_for_removal']='Not enough available data prior or post index date'
    removed_pts.to_csv('data/pt_data/removed_pts.csv',mode='a',index=False)
    pt_features=pt_features.loc[row_index == False]

    pt_features.to_csv('data/pt_data/pt_features.csv',index=False)

def match_cases_and_controls():
    pt_features = pd.read_csv('data/pt_data/pt_features.csv',delimiter=',',parse_dates=['index_date','earliest_sysdate','latest_sysdate'])

    pt_features['new_match_id']=np.nan

    count=0
    for index,row in pt_features.iterrows():
        if(row['isCase']==True):
            if pd.isnull(row['new_match_id']):
                patid = row['patid']
                birthyear = row['birthyear']
                gender = row['gender']
                pracid = row['pracid']
                index_date = row['index_date']
                # Define matching criteria
                matches_birthyear = pt_features['birthyear']==birthyear
                matches_gender = pt_features['gender']==gender
                is_control = pt_features['isCase'] == False
                matches_practice = pt_features['pracid']==pracid
                is_not_already_matched = pd.isnull(pt_features['new_match_id'])
                enough_data_after_index_date = pt_features['earliest_sysdate'] <= (index_date - timedelta(days=(365*Study_Design.total_years_required_pre_index_date)))
                enough_data_before_index_date = pt_features['latest_sysdate'] >= (index_date + timedelta(days=(365*Study_Design.years_of_data_after_index_date_required_by_controls)))
                matching_pt = pt_features[enough_data_before_index_date & enough_data_after_index_date & matches_birthyear & matches_gender & matches_practice & is_control & is_not_already_matched].head(1)
                if len(matching_pt)>0:
                    #give both the case and control a unique match ID (for convenience, I've used the iterrows index)
                    matching_pt_id = int(matching_pt['patid'].values[0])
                    matching_pt_index = pt_features['patid']==matching_pt_id
                    pt_features.loc[index,'new_match_id']=index
                    pt_features.loc[matching_pt_index,'new_match_id']=index
                    pt_features.loc[matching_pt_index,'index_date']=index_date
                    # print('Matched {0} with {1}.'.format(patid,matching_pt_id))
                    count += 1
        if count>100:
            pt_features.to_csv('data/pt_data/pt_features.csv',index=False)
            # print('***WRITING TO FILE***')
            count=0

def delete_unmatched_controls():
    pt_features = pd.read_csv('data/pt_data/pt_features.csv',delimiter=',',parse_dates=['index_date','earliest_sysdate','latest_sysdate'])
    removed_unmatched_controls = pt_features[pd.isnull(pt_features['new_match_id'])]
    removed_unmatched_controls.to_csv('data/pt_data/removed_unmatched_controls.csv',index=False)
    pt_features = pt_features[pd.notnull(pt_features['new_match_id'])]
    pt_features.to_csv('data/pt_data/pt_features.csv',index=False)

def create_insomnia_medcodes():
    """
    creates csv files containing all the insomnia medcodes, based on insomnia_readcodes.csv
    """
    pegmed = pd.read_csv('data/dicts/proc_pegasus_medical.csv')
    readcodes = pd.read_csv('data/codelists/insomnia_readcodes.csv',delimiter=',')
    medcodes=[str(pegmed.loc[pegmed['readcode']==readcode]['medcode'].iloc[0]) for readcode in readcodes]
    with open('data/codelists/insomnia_medcodes.csv','w', newline='') as f:
        writer = csv.writer(f,delimiter=',',quotechar='|', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(medcodes)

def get_insomnia_medcodes():
    medcodes = pd.read_csv('data/codelists/insomnia_medcodes.csv',delimiter=',')
    return [int(medcode) for medcode in list(medcodes)]

def create_insomnia_entries():
    """
    Creates csv file containing all medcoded entries (tests, referrals, clinicals) relating to our insomnia medcodes
    """
    df = pd.read_csv('data/pt_data/medcoded_entries.csv',delimiter=',')
    medcodes = get_insomnia_medcodes()
    relev_clinical = df[df['medcode'].isin(medcodes)]
    relev_clinical.to_csv('data/pt_data/all_insomnia_entries.csv',index=False)

def add_insomnia_event_count_to_pt_features():
    """
    Calculates count of insomnia-months for each patient, and adds it to pt_features dataframe
    """
    # Load list of all insomnia entries, then group it to calculate each patient's insomnia count, broken down by month
    insom_events = pd.read_csv('data/pt_data/all_insomnia_entries.csv',delimiter=',',parse_dates=['eventdate'])
    insom_events=insom_events[pd.notnull(insom_events['eventdate'])] #drops a small number of rows (only about 64) with NaN eventdates
    insom_events=insom_events[['patid','eventdate']].set_index('eventdate').groupby('patid').resample('M').count()
    #convert group_by object back to dataframe
    insom_events = insom_events.add_suffix('_count').reset_index()
    insom_events.columns=['patid','eventdate','insom_count']
    #delete zero counts
    insom_events=insom_events[insom_events['insom_count']>0]

    pt_features = pd.read_csv('data/pt_data/pt_features.csv',delimiter=',',parse_dates=['index_date'])

    # Remove insomnia events for patients who are no longer in study (e.g. because I've removed them for not having any enough data)
    insom_events['pat_in_study'] = insom_events['patid'].map(lambda x: x if any(pt_features.patid==x) else np.nan)

    insom_events=insom_events[pd.notnull(insom_events['pat_in_study'])]
    insom_events['pat_in_study']=insom_events['pat_in_study'].astype(int)

    insom_events['pat_index_date']=np.nan
    insom_events['pat_index_date'] = insom_events['patid'].map(lambda x: pt_features[pt_features['patid']==x]['index_date'].values[0])

    # Restrict insomnia event counts to those that occur during exposure period
    too_close_to_dx_period = timedelta(days=365)*Study_Design.years_between_exposure_measurement_and_index_date
    too_distant_from_dx_period = too_close_to_dx_period + timedelta(days=365)*Study_Design.years_of_exposure_measurement
    not_too_close_to_dx = insom_events['eventdate']<(insom_events['pat_index_date']-too_close_to_dx_period)
    not_before_exposure_period = insom_events['eventdate']>(insom_events['pat_index_date']-too_distant_from_dx_period)
    relev_insom_events = insom_events[not_too_close_to_dx & not_before_exposure_period]

    # Convert groupby object into a dataframe, and rename new column
    relev_insom_events_by_pt = relev_insom_events.groupby(by='patid')['eventdate'].count().reset_index()
    relev_insom_events_by_pt.columns=['patid','insomnia_event_count']

    # merge pt_features with new relev_insomnia_event dataframe
    merged_table = pd.merge(pt_features,relev_insom_events_by_pt, on='patid',how='outer')
    merged_table['insomnia_event_count'].fillna(0,inplace=True)
    merged_table['insomnia_event_count'] = merged_table['insomnia_event_count'].astype(int)

    merged_table.to_csv('data/pt_data/pt_features.csv',index=False)
