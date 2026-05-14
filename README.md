# libseraph

A hot new dataset management tool that's crazy easy!

## Motivation

There is no generally accepted metadata standard for multimedia data, and no tooling for multimedia dataset (meta)data management. At the outset of TEAM-ML, creating a training dataset was an error-prone process that typically required 8-20 hours of work from an ML expert, at a total cost of $1,200-$3,000.

To expedite the creation and refinement of training datasets, we developed an absolute minimum metadata standard for our multimedia datasets and a management tool that covers all our common use cases.

In our experience, it requires 0.5-3 hours to prepare a component dataset for Seraph management with a bespoke script. This is a non-recurring cost that depends on the original dataset format and the delta between that format and the Seraph format. Once all component datasets are configured, a training dataset can be assembled in 5-30 _minutes_, depending on (1) the user’s understanding of the tooling and the desired end composition and (2) whether the component dataset(s) can be copied in as-is or if the data needs to be resampled/resized/etc. Seraph is particularly useful for creating special-purpose or exploratory datasets from existing components; we were able to create a “9mm Parabellum Cartridge Dataset” at a cost of <$10.

Seraph currently supports only audio datasets, as anything else is out of scope for TEAM-ML.

## Installation

```bash
conda create --name seraph python=3.12
conda activate seraph

pip install -r requirements.txt
pip install .

conda deactivate
```

### Compatibility Note

Other Python ML libraries from Certus Innovations use PyTorch 2.10 and the `torchcodec` library for loading audio. Unfortunately, the `torchcodec` library does not support enough options to save files for `seraph`, so it currently must rely on `torchaudio`, which limits the PyTorch version to 2.8. Using Conda or `venv` this isn't too hard to work around, but we are actively working on a path to upgrade this library for compatibility of our packages.

## Usage

The most used features of the Seraph tool are:

- Audio
  - Import audio data from other datasets, including allowing class selection and exclusion
  - Generate duration metadata
  - Clip audio data to a set length while preserving original track identity data
  - Resample audio
  - Prune empty audio files
- Classes
  - Switch class columns
  - Rename, merge, regex merge, and drop classes by name
  - Check class balance, including by fold/split
  - Compose class metadata from existing column(s)
- Metadata
  - Initialize a new seraph dataset
  - Verify all data items against the dataset contract specified in the metadata file
- Provenance
  - Prototype OpenIRIS integration for showing and submitting provenance
- Prune
  - Remove records with no corresponding files and vice versa
  - Drop data by row value
  - Drop metadata columns
- Splits
  - Automatically generate train/test/validate splits or cross-validation folds with respect to class balance and optionally avoid pseudoreplication
- Version
  - Prototype dataset version management by at least one [community standard](https://github.com/dslp/dslp/blob/main/semantic-versioning.md)
- Integrations
  -Prototype Fuel AI metadata format export

### Examples

```bash
# Activate environment
conda activate seraph

# Initialize new dataset
seraph meta init

# Import audio datasets
seraph audio import --import_dir ~/Desktop/Kaggle_Gunshots/
seraph audio import --import_dir ~/Desktop/Cadre_Forensics/ --channel_merge_strat mix_down --sample_rate_merge_strat mix_down

# Switch classes from `gun_type` to `caliber`
seraph classes switch --new_class_col caliber --new_name_for_current_class_col gun_type

# Merge degenerate classes
seraph classes merge --target_class_name 9x19 --classes_to_merge "9mm Luger" --classes_to_merge "9mm"

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

## Feature Wish-List

- **IDEMPOTENCE**
  - Prevent a dataset from being "double-tapped"
- Pipe dreams
  - Undo

## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the [tags on this repository](https://github.com/Stonewall-Defense/libseraph/tags).

## Authors

- **Ryan Quinn** - _Initial work_

## License

MIT.
