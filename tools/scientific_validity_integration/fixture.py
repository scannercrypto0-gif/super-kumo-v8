"""TEST_ONLY schema-shaped metadata; no original or artificial price simulation."""
from .integration import owner_digest


def fixture():
    bars=[{'bar_open_ms':1706745600000+i*900000,'bar_close_ms':1706745600000+(i+1)*900000-1,
        'checksum':owner_digest({'TEST_ONLY_BAR':i}),'availability_kind':'RETROSPECTIVE',
        'historical_known_at_ms':None} for i in range(2)]
    shared={'dataset_id':'TEST_ONLY_EVIDENCE_SEAM','version':1,'source_bytes_sha256':'a'*64,
        'manifest_integrity_sha256':'b'*64,'decision_cutoff_ms':1706747400000,'coverage':'COMPLETE',
        'missing_bar_opens':[],'available_bar_count':2,'required_bar_count':2}
    a=shared|{'schema':'aql.core.historical-original-admission.v1','authenticated_source':'NOT_ATTESTED',
        'confirmed_pit':'NOT_ATTESTED','correction_parent_source_sha256':None,
        'native_csv_member_sha256':'c'*64,'native_checksum_file_sha256':'d'*64}
    q=shared|{'schema':'aql.core.historical-price-custody-query.v1','status':'OK','scientific_pit':'NOT_ATTESTED',
        'source_availability':'RETROSPECTIVE_NON_PIT','bars':bars}
    a['manifest_record_sha256']=owner_digest(a);q['price_query_sha256']=owner_digest(q)
    return {'admission':a,'prices':q}


def chronology(n):
    a=n['admission'];b=n['prices']['bars'][0]
    c={'schema':'aql.core.historical-chronology-evidence.v1','dataset_id':a['dataset_id'],'version':1,
       'original_zip_sha256':a['source_bytes_sha256'],'manifest_integrity_sha256':a['manifest_integrity_sha256'],
       'issuer_name':'TEST_ONLY_CLAIM','evidence_reference':'TEST_ONLY_NO_INDEPENDENT_WITNESS',
       'evidence_bytes_sha256':'e'*64,'observed_capture_ms':1706747500000,'claimed_publication_ms':None,
       'claimed_historical_known_at_ms':None,'correction_state':'UNKNOWN','correction_parent_sha256':None,
       'bar_claims':[{'bar_open_ms':b['bar_open_ms'],'bar_checksum':b['checksum'],
          'claimed_known_at_ms':b['bar_close_ms']+1,'evidence_record_sha256':'f'*64}]}
    c['evidence_sha256']=owner_digest(c);return c
