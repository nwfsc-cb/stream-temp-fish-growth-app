import os

# Using pydex files from Riverscapes Data Consortisum open source material
# https://github.com/Riverscapes/data-exchange-scripts

from pydex.classes.riverscapes_helpers import RiverscapesSearchParams
from pydex.classes.RiverscapesAPI import RiverscapesAPI

def download_huc_data(huc_prefix, download_dir):
    '''Downloads riverscapes data for a given HUC.'''

    os.makedirs(download_dir, exist_ok=True)

    with RiverscapesAPI(stage='production') as api:
        params = RiverscapesSearchParams({
            'projectTypeId': 'streamtemp',
            'meta': {'HUC': f"{huc_prefix}"},
            'excludeArchived': True,
        })

        total, _ = api.search_count(params)

        for project, _, total, progress_bar in api.search(params, progress_bar=True):
            if not project.huc:
                continue

            project_dir = os.path.join(download_dir, project.huc)
            os.makedirs(project_dir, exist_ok=True)

            api.download_files(
                project_id=project.id,
                download_dir=project_dir,
                re_filter=[r'.*\.gpkg$', r'.*daily_stream_temperature.parquet\.gz'],
            )

    return f"Done! Downloaded files for HUC {huc_prefix} into '{download_dir}'."
