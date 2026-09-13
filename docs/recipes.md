# Recipes

Generated from the registry by `scripts/gen_recipe_docs.py`. Do not edit by hand;
edit the recipe and regenerate.

A recipe is declared once and becomes callable from Python, the CLI, the API, and
the agent. Every run goes through `registry.run`, which checks the QC gate,
evaluates guardrails before anything is computed, opens a run record, and writes
the outputs.

    python -m dbsspeech run <recipe> --subject <study_id> --claim "..." \
        --set <param>=<value>

A parameter left unset uses the default in the table. Defaults shown as `null`
are resolved elsewhere, from a config file the recipe names in its description.


## Registered

- [`bandpower_contrast`](#bandpower_contrast) version 1: Band power per derivation and condition, with permutation-tested contrasts and bootstrap confidence intervals. No parametric tests.
- [`erna`](#erna) version 1: Amplitude, frequency, and decay of evoked resonant neural activity after each stimulation event. Every setting that shapes the answer is a parameter, defaulting to configs/erna.yaml.
- [`erp_epochs`](#erp_epochs) version 1: Event-locked averages from a recording's own task markers, with per-trial baseline correction, trial counts on every row, and peak latency measured only inside a stated window.
- [`pac_modulation_index`](#pac_modulation_index) version 1: Phase-amplitude coupling per derivation and condition, by pactools Comodulogram, with surrogate correction and the waveform-shape caveat stated on every result.
- [`psd_by_condition`](#psd_by_condition) version 1: Power spectral density per derivation and condition, under every montage, reported in dB alongside a z against a chosen baseline.
- [`pynm_features`](#pynm_features) version 1: py_neuromodulation's feature set computed on approved data, with their settings driven by our config and their re-referencing switched off.
- [`tfr_onset`](#tfr_onset) version 1: Time-frequency power around the onset of each condition window, baselined against the pre-onset period, averaged within region.


## bandpower_contrast

Version 1. Band power per derivation and condition, with permutation-tested contrasts and bootstrap confidence intervals. No parametric tests.

| parameter | type | default | what it does |
|---|---|---|---|
| `claimed_event_duration_s` | number | null | Duration in seconds of the event this run is claiming, if it claims one: a burst, a response, a transient. Guardrail G5 compares it to the analysis window, because a window several times longer than the event integrates over many of them and cannot resolve one. Leave it unset when the run makes no claim about an event, and G5 stays quiet: a guardrail cannot judge a claim nobody made. |
| `leads` | list[string] | null | None means every lead. |
| `conditions` | list[string] | null | None means every condition in the manifest. |
| `contrasts` | list[array] | null | Condition pairs to compare, as [a, b]. None means every pair present, which keeps the comparison symmetric rather than privileging one. |
| `bands` | object | null | None means the bands in configs/bands.yaml. |
| `unit` | window | pseudo_epoch | `pseudo_epoch` | pseudo_epoch gives an n so a contrast can be tested, at the cost that epochs from one recording are not independent. window gives one observation per condition and no test at all. |
| `epoch_s` | number | `2.0` |  |
| `epoch_overlap` | number | `0.0` | Overlap makes epochs even less independent. |
| `references` | list[string] | null |  |
| `primary_reference` | string | `bipolar_vertical` |  |
| `sfreq_target_hz` | number | `8138.0` |  |
| `method` | welch | multitaper | `welch` |  |
| `window_s` | number | `1.0` |  |
| `fmin` | number | `1.0` |  |
| `fmax` | number | `200.0` |  |
| `log10` | boolean | `True` | Work in dB. Ratios become differences. |
| `n_permutations` | integer | `5000` |  |
| `n_bootstrap` | integer | `2000` |  |
| `seed` | integer | `0` | Recorded, so a p-value is reproducible. |
| `baseline_center` | grand_mean | condition | whole_recording | none | `grand_mean` |  |
| `baseline_scale` | pooled_within_condition | own_condition | condition | across_conditions | none | `pooled_within_condition` |  |
| `baseline_condition` | string | `rest` |  |


### centers

- **grand_mean** (Grand mean across conditions): Compare each condition against the average of all conditions in the run.
  - when to use: When no condition is a trustworthy baseline, or when you want a symmetric comparison that does not privilege one condition.
  - caveat: The centre moves when you change which conditions are included, so two runs over different condition sets are not directly comparable.
- **condition** (A named baseline condition): Compare every condition against one chosen condition, usually rest.
  - when to use: The conventional framing, and the one most directly comparable to published work and to figures you have already produced.
  - caveat: Inherits everything wrong with the baseline window. If that window is under revision, every result depending on it is flagged by guardrail G10.
- **whole_recording** (All segments pooled): Compare against the mean over every segment in the run, weighted by how much data each condition contributed.
  - when to use: When conditions differ a lot in duration and you want the longer ones to carry more weight in defining the centre.
  - caveat: The task periods sit inside their own baseline, which shrinks every effect toward zero by construction. The more of the recording is task, the worse.
- **none** (No centring): Do not subtract anything. z becomes the value divided by the scale.
  - when to use: When you want a signal-to-noise ratio rather than a contrast.
  - caveat: Not a contrast, and should not be described as one. It is also the only centre that carries the dB column's absolute offset into z. The recipe converts each segment to decibels before averaging them, which biases every dB value low by a constant: 2.51 dB on the Welch method, where each segment is one periodogram, and 0.31 dB on multitaper, which averages over tapers first. Every other centre subtracts one dB value from another and the constant cancels. Here nothing is subtracted, so at a scale of 2 dB the offset alone is more than one z unit. Measured in curriculum/10_stochastic/01_estimators_are_random_variables.


### scales

- **pooled_within_condition** (Pooled within-condition variability): Pool the per-condition standard deviations into one number and use it for every condition: the square root of the segment-weighted mean of the variances, sqrt(sum((n_i - 1) * s_i^2) / sum(n_i - 1)). Until 2026-09-09 this averaged the standard deviations instead, which is a systematically smaller number whenever the conditions differ in variability, so every z computed on this default before that date was inflated. See docs/findings.md.
  - when to use: The default. One scale for all conditions, so a difference of the same size reads the same wherever it occurs.
  - caveat: A single noisy condition inflates the pooled scale and shrinks every z, including in the quiet conditions.
- **own_condition** (Each condition's own variability): Scale each condition by how much it varies across its own time segments.
  - when to use: When conditions genuinely differ in stability and you want each judged on its own terms.
  - caveat: A noisy condition gets a smaller z purely for being noisy, which understates real effects in exactly the conditions where they are hardest to see.
- **condition** (The baseline condition's variability): Scale everything by the spread of the named baseline condition.
  - when to use: Pairs naturally with a named baseline centre: how many baseline standard deviations away is this.
  - caveat: If the baseline window is short or atypical, its spread is a poor yardstick and every z inherits that.
- **across_conditions** (Spread between condition means): Scale by how much the condition means differ from each other, ignoring within-condition variability.
  - when to use: When you care about which condition stands out relative to the others, rather than relative to moment-to-moment noise.
  - caveat: With few conditions this is estimated from very few numbers and is unstable. Meaningless with fewer than three.
- **none** (No scaling): Divide by one. z is then just the centred value, in dB.
  - when to use: When dB differences are already the quantity you want to read.
  - caveat: Do not call the result a z score; it is a difference in decibels.


## erna

Version 1. Amplitude, frequency, and decay of evoked resonant neural activity after each stimulation event. Every setting that shapes the answer is a parameter, defaulting to configs/erna.yaml.

| parameter | type | default | what it does |
|---|---|---|---|
| `leads` | list[string] | null | None means every lead. |
| `primary_reference` | string | `bipolar_vertical` | ERNA is recorded on the stimulating lead, so a montage that keeps per-contact identity is usually what you want. |
| `references` | list[string] | null | None means the primary reference only. |
| `sfreq_target_hz` | number | null | None keeps the recording's own rate. ERNA lives in the hundreds of hertz, so decimating far is how you lose it. Guardrail G6 refuses a band above the anti-alias cutoff. |
| `stim_source` | amplitude_threshold | windows | epochs | null | How stimulation events are located: the artifact in the signal, condition windows from the manifest, or an epoch store in the recording. |
| `stim_threshold_mad` | number | null | amplitude_threshold only. Median absolute deviations above the median that count as an artifact. |
| `stim_refractory_ms` | number | null | Minimum spacing between events. This is what stops one artifact being counted as several; set it just under the spacing of the events you want counted separately. |
| `stim_condition` | string | null | windows source: which condition's windows are events. |
| `stim_epoch_store` | string | null | epochs source: which epoch store, by name. |
| `max_events` | integer | `500` | Cap on events analyzed, oldest first. A recording with thousands is usually a detection that is firing on noise. |
| `blanking_ms` | number | null | Milliseconds discarded after each event. The single most consequential setting here. |
| `analysis_ms` | number | null | Milliseconds analyzed after the blanking. |
| `bandpass_low_hz` | number | null |  |
| `bandpass_high_hz` | number | null |  |
| `min_peaks` | integer | null | Fewest successive peaks for an epoch to be measured at all. |
| `min_prominence_fraction` | number | null |  |
| `max_interval_jitter` | number | null | How far one interval between extrema may differ from the ones before it before the resonance is considered over. This is what stops noise after the ringing being measured as part of it. |
| `fit_decay` | boolean | null |  |
| `min_r_squared` | number | null |  |
| `max_frequency_disagreement` | number | null |  |


## erp_epochs

Version 1. Event-locked averages from a recording's own task markers, with per-trial baseline correction, trial counts on every row, and peak latency measured only inside a stated window.

| parameter | type | default | what it does |
|---|---|---|---|
| `event_label` | string | null | Marker label to lock to, as the reader reports it. None lists the labels the recording carries and refuses, rather than picking one. |
| `condition` | string | null | Restrict to events falling inside this condition's windows. None uses every event in the recording. |
| `leads` | list[string] | null | None means every lead. |
| `references` | list[string] | null |  |
| `primary_reference` | string | `bipolar_vertical` |  |
| `tmin_s` | number | `-0.2` | Epoch start relative to the event, usually negative. |
| `tmax_s` | number | `0.8` | Epoch end relative to the event. |
| `baseline_start_s` | number | `-0.2` |  |
| `baseline_end_s` | number | `0.0` | Must be at or before 0: a baseline overlapping the response subtracts the response from itself. |
| `peak_window_start_s` | number | `0.0` |  |
| `peak_window_end_s` | number | `0.5` | Peak amplitude and latency are measured only inside this window, so the search range is stated rather than chosen after seeing the data. |
| `min_trials` | integer | `10` | Below this, no average is produced. An average over a handful of trials is not an ERP. |
| `sfreq_target_hz` | number | `1000.0` |  |


### centers

- **grand_mean** (Grand mean across conditions): Compare each condition against the average of all conditions in the run.
  - when to use: When no condition is a trustworthy baseline, or when you want a symmetric comparison that does not privilege one condition.
  - caveat: The centre moves when you change which conditions are included, so two runs over different condition sets are not directly comparable.
- **condition** (A named baseline condition): Compare every condition against one chosen condition, usually rest.
  - when to use: The conventional framing, and the one most directly comparable to published work and to figures you have already produced.
  - caveat: Inherits everything wrong with the baseline window. If that window is under revision, every result depending on it is flagged by guardrail G10.
- **whole_recording** (All segments pooled): Compare against the mean over every segment in the run, weighted by how much data each condition contributed.
  - when to use: When conditions differ a lot in duration and you want the longer ones to carry more weight in defining the centre.
  - caveat: The task periods sit inside their own baseline, which shrinks every effect toward zero by construction. The more of the recording is task, the worse.
- **none** (No centring): Do not subtract anything. z becomes the value divided by the scale.
  - when to use: When you want a signal-to-noise ratio rather than a contrast.
  - caveat: Not a contrast, and should not be described as one. It is also the only centre that carries the dB column's absolute offset into z. The recipe converts each segment to decibels before averaging them, which biases every dB value low by a constant: 2.51 dB on the Welch method, where each segment is one periodogram, and 0.31 dB on multitaper, which averages over tapers first. Every other centre subtracts one dB value from another and the constant cancels. Here nothing is subtracted, so at a scale of 2 dB the offset alone is more than one z unit. Measured in curriculum/10_stochastic/01_estimators_are_random_variables.


### scales

- **pooled_within_condition** (Pooled within-condition variability): Pool the per-condition standard deviations into one number and use it for every condition: the square root of the segment-weighted mean of the variances, sqrt(sum((n_i - 1) * s_i^2) / sum(n_i - 1)). Until 2026-09-09 this averaged the standard deviations instead, which is a systematically smaller number whenever the conditions differ in variability, so every z computed on this default before that date was inflated. See docs/findings.md.
  - when to use: The default. One scale for all conditions, so a difference of the same size reads the same wherever it occurs.
  - caveat: A single noisy condition inflates the pooled scale and shrinks every z, including in the quiet conditions.
- **own_condition** (Each condition's own variability): Scale each condition by how much it varies across its own time segments.
  - when to use: When conditions genuinely differ in stability and you want each judged on its own terms.
  - caveat: A noisy condition gets a smaller z purely for being noisy, which understates real effects in exactly the conditions where they are hardest to see.
- **condition** (The baseline condition's variability): Scale everything by the spread of the named baseline condition.
  - when to use: Pairs naturally with a named baseline centre: how many baseline standard deviations away is this.
  - caveat: If the baseline window is short or atypical, its spread is a poor yardstick and every z inherits that.
- **across_conditions** (Spread between condition means): Scale by how much the condition means differ from each other, ignoring within-condition variability.
  - when to use: When you care about which condition stands out relative to the others, rather than relative to moment-to-moment noise.
  - caveat: With few conditions this is estimated from very few numbers and is unstable. Meaningless with fewer than three.
- **none** (No scaling): Divide by one. z is then just the centred value, in dB.
  - when to use: When dB differences are already the quantity you want to read.
  - caveat: Do not call the result a z score; it is a difference in decibels.


## pac_modulation_index

Version 1. Phase-amplitude coupling per derivation and condition, by pactools Comodulogram, with surrogate correction and the waveform-shape caveat stated on every result.

| parameter | type | default | what it does |
|---|---|---|---|
| `leads` | list[string] | null | None means every lead. |
| `conditions` | list[string] | null | None means every condition in the manifest. |
| `references` | list[string] | null | None means every scheme. |
| `primary_reference` | string | `bipolar_vertical` |  |
| `phase_fq_min_hz` | number | `4.0` |  |
| `phase_fq_max_hz` | number | `40.0` |  |
| `phase_fq_step_hz` | number | `2.0` |  |
| `phase_fq_width_hz` | number | `2.0` | Bandwidth of the phase filter, in Hz. Keep it at or below phase_fq_step_hz: wider than the step means neighbouring bins admit the same rhythm, the phase axis stops discriminating, and the reported peak moves to whichever bin noise favours. |
| `amplitude_fq_min_hz` | number | `50.0` |  |
| `amplitude_fq_max_hz` | number | `200.0` |  |
| `amplitude_fq_step_hz` | number | `10.0` |  |
| `amplitude_fq_width_hz` | number | null | Bandwidth of the amplitude filter, in Hz. None means pactools' 'auto', which is twice the highest phase frequency. That is the sideband condition: the amplitude filter must be wide enough to contain the phase frequency as a sideband, or coupling that exists cannot appear at all. |
| `method` | tort | canolty | ozkurt | penny | vanwijk | `tort` | tort is the modulation index, the most reported and so the most comparable. The estimators disagree on the same data, so this travels into the run record. |
| `n_surrogates` | integer | `200` | A modulation index is positive for noise, so a null is not optional. 0 disables surrogates and the summary then says the value is uncorrected. |
| `sfreq_target_hz` | number | `1000.0` |  |
| `seed` | integer | `0` |  |


### centers

- **grand_mean** (Grand mean across conditions): Compare each condition against the average of all conditions in the run.
  - when to use: When no condition is a trustworthy baseline, or when you want a symmetric comparison that does not privilege one condition.
  - caveat: The centre moves when you change which conditions are included, so two runs over different condition sets are not directly comparable.
- **condition** (A named baseline condition): Compare every condition against one chosen condition, usually rest.
  - when to use: The conventional framing, and the one most directly comparable to published work and to figures you have already produced.
  - caveat: Inherits everything wrong with the baseline window. If that window is under revision, every result depending on it is flagged by guardrail G10.
- **whole_recording** (All segments pooled): Compare against the mean over every segment in the run, weighted by how much data each condition contributed.
  - when to use: When conditions differ a lot in duration and you want the longer ones to carry more weight in defining the centre.
  - caveat: The task periods sit inside their own baseline, which shrinks every effect toward zero by construction. The more of the recording is task, the worse.
- **none** (No centring): Do not subtract anything. z becomes the value divided by the scale.
  - when to use: When you want a signal-to-noise ratio rather than a contrast.
  - caveat: Not a contrast, and should not be described as one. It is also the only centre that carries the dB column's absolute offset into z. The recipe converts each segment to decibels before averaging them, which biases every dB value low by a constant: 2.51 dB on the Welch method, where each segment is one periodogram, and 0.31 dB on multitaper, which averages over tapers first. Every other centre subtracts one dB value from another and the constant cancels. Here nothing is subtracted, so at a scale of 2 dB the offset alone is more than one z unit. Measured in curriculum/10_stochastic/01_estimators_are_random_variables.


### scales

- **pooled_within_condition** (Pooled within-condition variability): Pool the per-condition standard deviations into one number and use it for every condition: the square root of the segment-weighted mean of the variances, sqrt(sum((n_i - 1) * s_i^2) / sum(n_i - 1)). Until 2026-09-09 this averaged the standard deviations instead, which is a systematically smaller number whenever the conditions differ in variability, so every z computed on this default before that date was inflated. See docs/findings.md.
  - when to use: The default. One scale for all conditions, so a difference of the same size reads the same wherever it occurs.
  - caveat: A single noisy condition inflates the pooled scale and shrinks every z, including in the quiet conditions.
- **own_condition** (Each condition's own variability): Scale each condition by how much it varies across its own time segments.
  - when to use: When conditions genuinely differ in stability and you want each judged on its own terms.
  - caveat: A noisy condition gets a smaller z purely for being noisy, which understates real effects in exactly the conditions where they are hardest to see.
- **condition** (The baseline condition's variability): Scale everything by the spread of the named baseline condition.
  - when to use: Pairs naturally with a named baseline centre: how many baseline standard deviations away is this.
  - caveat: If the baseline window is short or atypical, its spread is a poor yardstick and every z inherits that.
- **across_conditions** (Spread between condition means): Scale by how much the condition means differ from each other, ignoring within-condition variability.
  - when to use: When you care about which condition stands out relative to the others, rather than relative to moment-to-moment noise.
  - caveat: With few conditions this is estimated from very few numbers and is unstable. Meaningless with fewer than three.
- **none** (No scaling): Divide by one. z is then just the centred value, in dB.
  - when to use: When dB differences are already the quantity you want to read.
  - caveat: Do not call the result a z score; it is a difference in decibels.


## psd_by_condition

Version 1. Power spectral density per derivation and condition, under every montage, reported in dB alongside a z against a chosen baseline.

| parameter | type | default | what it does |
|---|---|---|---|
| `leads` | list[string] | null | Lead ids to run. None means every lead in the manifest. |
| `conditions` | list[string] | null | Conditions to run. None means every window in the manifest. |
| `unit` | window | pseudo_epoch | `window` | window: one row per condition, covering the whole window. Its db_sd is the spread across the spectral segments inside that window, not an n=1 quantity, so read it as local variability rather than as a trial-level error. pseudo_epoch: fixed epochs give one row each; db_sd is still the within-epoch segment spread, and the epochs are not independent of one another. |
| `epoch_s` | number | `2.0` | Pseudo-epoch length, seconds. |
| `epoch_overlap` | number | `0.5` | Pseudo-epoch overlap fraction. |
| `references` | list[string] | null | Montages to compute. None means all of them. |
| `primary_reference` | string | `bipolar_vertical` | Montage used for the headline figure. |
| `sfreq_target_hz` | number | `8138.0` | Decimate toward this rate. Usable bandwidth is 0.4x it. |
| `claimed_event_duration_s` | number | null | Duration in seconds of the event this run is claiming, if it claims one: a burst, a response, a transient. Guardrail G5 compares it to the analysis window, because a window several times longer than the event integrates over many of them and cannot resolve one. Leave it unset when the run makes no claim about an event, and G5 stays quiet: a guardrail cannot judge a claim nobody made. |
| `band_of_interest` | string | `beta` | Band from configs/bands.yaml that this run is about. It selects the headline peak in the summary and supplies guardrail G9's excursion and effect. One band for both, because the effect G9 weighs against the baseline should be the effect the run reports. |
| `method` | welch | multitaper | `welch` |  |
| `window_s` | number | `1.0` | Spectral window, seconds. |
| `fmin` | number | `1.0` |  |
| `fmax` | number | `200.0` |  |
| `baseline_center` | grand_mean | condition | whole_recording | none | `grand_mean` | What each condition is compared against. See configs/statistics.yaml. |
| `baseline_scale` | pooled_within_condition | own_condition | condition | across_conditions | none | `pooled_within_condition` | What counts as a large difference. See configs/statistics.yaml. |
| `baseline_condition` | string | `rest` | Which condition acts as the baseline, when centre or scale is 'condition'. |


### centers

- **grand_mean** (Grand mean across conditions): Compare each condition against the average of all conditions in the run.
  - when to use: When no condition is a trustworthy baseline, or when you want a symmetric comparison that does not privilege one condition.
  - caveat: The centre moves when you change which conditions are included, so two runs over different condition sets are not directly comparable.
- **condition** (A named baseline condition): Compare every condition against one chosen condition, usually rest.
  - when to use: The conventional framing, and the one most directly comparable to published work and to figures you have already produced.
  - caveat: Inherits everything wrong with the baseline window. If that window is under revision, every result depending on it is flagged by guardrail G10.
- **whole_recording** (All segments pooled): Compare against the mean over every segment in the run, weighted by how much data each condition contributed.
  - when to use: When conditions differ a lot in duration and you want the longer ones to carry more weight in defining the centre.
  - caveat: The task periods sit inside their own baseline, which shrinks every effect toward zero by construction. The more of the recording is task, the worse.
- **none** (No centring): Do not subtract anything. z becomes the value divided by the scale.
  - when to use: When you want a signal-to-noise ratio rather than a contrast.
  - caveat: Not a contrast, and should not be described as one. It is also the only centre that carries the dB column's absolute offset into z. The recipe converts each segment to decibels before averaging them, which biases every dB value low by a constant: 2.51 dB on the Welch method, where each segment is one periodogram, and 0.31 dB on multitaper, which averages over tapers first. Every other centre subtracts one dB value from another and the constant cancels. Here nothing is subtracted, so at a scale of 2 dB the offset alone is more than one z unit. Measured in curriculum/10_stochastic/01_estimators_are_random_variables.


### scales

- **pooled_within_condition** (Pooled within-condition variability): Pool the per-condition standard deviations into one number and use it for every condition: the square root of the segment-weighted mean of the variances, sqrt(sum((n_i - 1) * s_i^2) / sum(n_i - 1)). Until 2026-09-09 this averaged the standard deviations instead, which is a systematically smaller number whenever the conditions differ in variability, so every z computed on this default before that date was inflated. See docs/findings.md.
  - when to use: The default. One scale for all conditions, so a difference of the same size reads the same wherever it occurs.
  - caveat: A single noisy condition inflates the pooled scale and shrinks every z, including in the quiet conditions.
- **own_condition** (Each condition's own variability): Scale each condition by how much it varies across its own time segments.
  - when to use: When conditions genuinely differ in stability and you want each judged on its own terms.
  - caveat: A noisy condition gets a smaller z purely for being noisy, which understates real effects in exactly the conditions where they are hardest to see.
- **condition** (The baseline condition's variability): Scale everything by the spread of the named baseline condition.
  - when to use: Pairs naturally with a named baseline centre: how many baseline standard deviations away is this.
  - caveat: If the baseline window is short or atypical, its spread is a poor yardstick and every z inherits that.
- **across_conditions** (Spread between condition means): Scale by how much the condition means differ from each other, ignoring within-condition variability.
  - when to use: When you care about which condition stands out relative to the others, rather than relative to moment-to-moment noise.
  - caveat: With few conditions this is estimated from very few numbers and is unstable. Meaningless with fewer than three.
- **none** (No scaling): Divide by one. z is then just the centred value, in dB.
  - when to use: When dB differences are already the quantity you want to read.
  - caveat: Do not call the result a z score; it is a difference in decibels.


## pynm_features

Version 1. py_neuromodulation's feature set computed on approved data, with their settings driven by our config and their re-referencing switched off.

| parameter | type | default | what it does |
|---|---|---|---|
| `claimed_event_duration_s` | number | null | Duration in seconds of the event this run is claiming, if it claims one: a burst, a response, a transient. Guardrail G5 compares it to the analysis window, because a window several times longer than the event integrates over many of them and cannot resolve one. Leave it unset when the run makes no claim about an event, and G5 stays quiet: a guardrail cannot judge a claim nobody made. |
| `leads` | list[string] | null |  |
| `conditions` | list[string] | null | None runs the whole recording and labels each feature row by whichever condition window it falls in. |
| `reference` | string | `bipolar_vertical` | Our montage, applied before the data is handed over. Their re-referencing is switched off so it is not applied twice. |
| `sfreq_target_hz` | number | `1000.0` |  |
| `features` | list[string] | null | None means their defaults minus the heavy ones. Naming a feature here enables exactly that set. |
| `sampling_rate_features_hz` | number | `10.0` |  |
| `segment_length_features_ms` | number | `1000.0` |  |
| `line_noise_hz` | number | `60.0` |  |
| `use_project_bands` | boolean | `True` | Drive their frequency ranges from configs/bands.yaml rather than their defaults. |


### centers

- **grand_mean** (Grand mean across conditions): Compare each condition against the average of all conditions in the run.
  - when to use: When no condition is a trustworthy baseline, or when you want a symmetric comparison that does not privilege one condition.
  - caveat: The centre moves when you change which conditions are included, so two runs over different condition sets are not directly comparable.
- **condition** (A named baseline condition): Compare every condition against one chosen condition, usually rest.
  - when to use: The conventional framing, and the one most directly comparable to published work and to figures you have already produced.
  - caveat: Inherits everything wrong with the baseline window. If that window is under revision, every result depending on it is flagged by guardrail G10.
- **whole_recording** (All segments pooled): Compare against the mean over every segment in the run, weighted by how much data each condition contributed.
  - when to use: When conditions differ a lot in duration and you want the longer ones to carry more weight in defining the centre.
  - caveat: The task periods sit inside their own baseline, which shrinks every effect toward zero by construction. The more of the recording is task, the worse.
- **none** (No centring): Do not subtract anything. z becomes the value divided by the scale.
  - when to use: When you want a signal-to-noise ratio rather than a contrast.
  - caveat: Not a contrast, and should not be described as one. It is also the only centre that carries the dB column's absolute offset into z. The recipe converts each segment to decibels before averaging them, which biases every dB value low by a constant: 2.51 dB on the Welch method, where each segment is one periodogram, and 0.31 dB on multitaper, which averages over tapers first. Every other centre subtracts one dB value from another and the constant cancels. Here nothing is subtracted, so at a scale of 2 dB the offset alone is more than one z unit. Measured in curriculum/10_stochastic/01_estimators_are_random_variables.


### scales

- **pooled_within_condition** (Pooled within-condition variability): Pool the per-condition standard deviations into one number and use it for every condition: the square root of the segment-weighted mean of the variances, sqrt(sum((n_i - 1) * s_i^2) / sum(n_i - 1)). Until 2026-09-09 this averaged the standard deviations instead, which is a systematically smaller number whenever the conditions differ in variability, so every z computed on this default before that date was inflated. See docs/findings.md.
  - when to use: The default. One scale for all conditions, so a difference of the same size reads the same wherever it occurs.
  - caveat: A single noisy condition inflates the pooled scale and shrinks every z, including in the quiet conditions.
- **own_condition** (Each condition's own variability): Scale each condition by how much it varies across its own time segments.
  - when to use: When conditions genuinely differ in stability and you want each judged on its own terms.
  - caveat: A noisy condition gets a smaller z purely for being noisy, which understates real effects in exactly the conditions where they are hardest to see.
- **condition** (The baseline condition's variability): Scale everything by the spread of the named baseline condition.
  - when to use: Pairs naturally with a named baseline centre: how many baseline standard deviations away is this.
  - caveat: If the baseline window is short or atypical, its spread is a poor yardstick and every z inherits that.
- **across_conditions** (Spread between condition means): Scale by how much the condition means differ from each other, ignoring within-condition variability.
  - when to use: When you care about which condition stands out relative to the others, rather than relative to moment-to-moment noise.
  - caveat: With few conditions this is estimated from very few numbers and is unstable. Meaningless with fewer than three.
- **none** (No scaling): Divide by one. z is then just the centred value, in dB.
  - when to use: When dB differences are already the quantity you want to read.
  - caveat: Do not call the result a z score; it is a difference in decibels.


## tfr_onset

Version 1. Time-frequency power around the onset of each condition window, baselined against the pre-onset period, averaged within region.

| parameter | type | default | what it does |
|---|---|---|---|
| `claimed_event_duration_s` | number | null | Duration in seconds of the event this run is claiming, if it claims one: a burst, a response, a transient. Guardrail G5 compares it to the analysis window, because a window several times longer than the event integrates over many of them and cannot resolve one. Leave it unset when the run makes no claim about an event, and G5 stays quiet: a guardrail cannot judge a claim nobody made. |
| `leads` | list[string] | null |  |
| `conditions` | list[string] | null |  |
| `references` | list[string] | null | None means the primary reference only. TFR is expensive; computing five montages multiplies the cost. |
| `primary_reference` | string | `bipolar_vertical` |  |
| `tmin` | number | `-2.0` | Seconds relative to window onset. |
| `tmax` | number | `8.0` | Seconds relative to window onset. |
| `fmin` | number | `2.0` |  |
| `fmax` | number | `150.0` |  |
| `n_freqs` | integer | `40` | Log-spaced between fmin and fmax. |
| `min_cycles` | number | `3.0` | Floor on the number of cycles per wavelet. Below about three the Morlet is a broadband envelope detector rather than a frequency estimate, so the frequency axis stops meaning what it says. |
| `n_cycles_factor` | number | `0.5` | n_cycles = freq * this. Higher means better frequency resolution and worse time resolution. |
| `method` | morlet | multitaper | `morlet` |  |
| `sfreq_target_hz` | number | `1000.0` | TFR is expensive; a lower rate is usually right. Guardrail G6 still refuses any band above the anti-alias cutoff. |
| `decim` | integer | `4` | Temporal decimation of the output. |
| `baseline_mode` | logratio | percent | zscore | none | `logratio` | How each frequency is normalized against the pre-onset baseline. |
| `baseline_tmin` | number | `-2.0` |  |
| `baseline_tmax` | number | `-0.25` |  |


### centers

- **grand_mean** (Grand mean across conditions): Compare each condition against the average of all conditions in the run.
  - when to use: When no condition is a trustworthy baseline, or when you want a symmetric comparison that does not privilege one condition.
  - caveat: The centre moves when you change which conditions are included, so two runs over different condition sets are not directly comparable.
- **condition** (A named baseline condition): Compare every condition against one chosen condition, usually rest.
  - when to use: The conventional framing, and the one most directly comparable to published work and to figures you have already produced.
  - caveat: Inherits everything wrong with the baseline window. If that window is under revision, every result depending on it is flagged by guardrail G10.
- **whole_recording** (All segments pooled): Compare against the mean over every segment in the run, weighted by how much data each condition contributed.
  - when to use: When conditions differ a lot in duration and you want the longer ones to carry more weight in defining the centre.
  - caveat: The task periods sit inside their own baseline, which shrinks every effect toward zero by construction. The more of the recording is task, the worse.
- **none** (No centring): Do not subtract anything. z becomes the value divided by the scale.
  - when to use: When you want a signal-to-noise ratio rather than a contrast.
  - caveat: Not a contrast, and should not be described as one. It is also the only centre that carries the dB column's absolute offset into z. The recipe converts each segment to decibels before averaging them, which biases every dB value low by a constant: 2.51 dB on the Welch method, where each segment is one periodogram, and 0.31 dB on multitaper, which averages over tapers first. Every other centre subtracts one dB value from another and the constant cancels. Here nothing is subtracted, so at a scale of 2 dB the offset alone is more than one z unit. Measured in curriculum/10_stochastic/01_estimators_are_random_variables.


### scales

- **pooled_within_condition** (Pooled within-condition variability): Pool the per-condition standard deviations into one number and use it for every condition: the square root of the segment-weighted mean of the variances, sqrt(sum((n_i - 1) * s_i^2) / sum(n_i - 1)). Until 2026-09-09 this averaged the standard deviations instead, which is a systematically smaller number whenever the conditions differ in variability, so every z computed on this default before that date was inflated. See docs/findings.md.
  - when to use: The default. One scale for all conditions, so a difference of the same size reads the same wherever it occurs.
  - caveat: A single noisy condition inflates the pooled scale and shrinks every z, including in the quiet conditions.
- **own_condition** (Each condition's own variability): Scale each condition by how much it varies across its own time segments.
  - when to use: When conditions genuinely differ in stability and you want each judged on its own terms.
  - caveat: A noisy condition gets a smaller z purely for being noisy, which understates real effects in exactly the conditions where they are hardest to see.
- **condition** (The baseline condition's variability): Scale everything by the spread of the named baseline condition.
  - when to use: Pairs naturally with a named baseline centre: how many baseline standard deviations away is this.
  - caveat: If the baseline window is short or atypical, its spread is a poor yardstick and every z inherits that.
- **across_conditions** (Spread between condition means): Scale by how much the condition means differ from each other, ignoring within-condition variability.
  - when to use: When you care about which condition stands out relative to the others, rather than relative to moment-to-moment noise.
  - caveat: With few conditions this is estimated from very few numbers and is unstable. Meaningless with fewer than three.
- **none** (No scaling): Divide by one. z is then just the centred value, in dB.
  - when to use: When dB differences are already the quantity you want to read.
  - caveat: Do not call the result a z score; it is a difference in decibels.
