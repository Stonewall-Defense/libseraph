# libseraph

A hot new dataset management tool that's crazy easy

## Installation

```bash
conda create --name seraph python=3.12
conda activate seraph

pip install -r requirements.txt
pip install .

conda deactivate
```

## Usage

```bash
# Activate environment
conda activate seraph

# Initialize new dataset
seraph meta init

# Import audio datasets
seraph audio import --import_dir ~/Desktop/TEAM-ML/datasets/component/dart/free-firearm-sounds/
seraph audio import --import_dir ~/Desktop/TEAM-ML/datasets/component/dart/Cadre_Reloaded/
seraph audio import --import_dir ~/Desktop/TEAM-ML/datasets/component/dart/GS_GF/
seraph audio import --import_dir ~/Desktop/TEAM-ML/datasets/component/dart/Kaggle_GS/ --channel_merge_strat mix_down --sample_rate_merge_strat mix_down

# Switch classes from `gun_type` to `caliber`
seraph classes switch --new_class_col caliber --new_name_for_current_class_col gun_type

# Merge degenerate classes
seraph classes merge --target_class_name 9x19 --classes_to_merge "9mm Luger" --classes_to_merge "9mm"
seraph classes merge --target_class_name ".22LR" --classes_to_merge "0.22"
seraph classes merge --target_class_name "7.62x39" --classes_to_merge "7.62x39mm"

# Add durations to columns and clip to 1 sec
seraph audio duration --metadata_column_conflict_strat replace
seraph audio clip --clip_duration_secs 1 --dry_run

# Show provenance data (WIP)
seraph prov show
seraph prov submit --activity_label "Make new gunshot dataset"

# Show verioning data (WIP)
seraph version show

# Cleanup
conda deactivate
```

## Testing

```bash
python3 -m coverage run -m unittest discover -s test -p "*_test.py" && python -m coverage report --skip-covered
python -m coverage html
```

### Tests to Write

- No Coverage
  - integrations
  - provenance
- Partial Coverage
  - meta
  - version

## TODO

- **IDEMPOTENCE**
  - Prevent a dataset from being "double-tapped"
- Pipe dreams
  - Undo
