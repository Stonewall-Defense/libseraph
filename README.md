# libseraph

A hot new dataset management tool that's crazy easy

## Usage

```bash
conda create --name seraph python=3.12
conda activate seraph
pip install -r requirements.txt

python3 exec.py init

python3 exec.py audio import --import_dir ~/Desktop/TEAM-ML/DART/seraph/free-firearm-sounds/
python3 exec.py audio import --import_dir ~/Desktop/TEAM-ML/DART/seraph/Cadre_Reloaded/
python3 exec.py audio import --import_dir ~/Desktop/TEAM-ML/DART/seraph/GS_GF/
python3 exec.py audio import --import_dir ~/Desktop/TEAM-ML/DART/seraph/Kaggle_GS/ --channel_merge_strat mix_down --sample_rate_merge_strat mix_down

python3 exec.py classes switch --new_class_col caliber --new_name_for_current_class_col gun_type
python3 exec.py classes merge --target_class_name 9x19 --classes_to_merge "9mm Luger" --classes_to_merge "9mm"
python3 exec.py classes merge --target_class_name ".22LR" --classes_to_merge "0.22"
python3 exec.py classes merge --target_class_name "7.62x39" --classes_to_merge "7.62x39mm"

python3 exec.py audio duration --metadata_column_conflict_strat replace
python3 exec.py audio clip --clip_duration_secs 1 --dry_run

python3 exec.py prov show
python3 exec.py prov submit --activity_label "Make new gunshot dataset"

python3 exec.py version show

conda deactivate
```

## TODO

- Prevent a dataset from being "double-tapped"
- Mark imports of partial datasets properly
- Delete matching criteria
- Undo
- Submit licenses
