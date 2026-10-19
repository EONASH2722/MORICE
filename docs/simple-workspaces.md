# Projects and Experiments

Projects creates or edits source files. Research runs supported computational experiments and stores their results. Normal Chats answers questions.

## Build a project

1. Open **Projects**. Builder mode is selected automatically.
2. Select **Choose folder** and choose an existing or new work folder outside the MORICE installation. If no folder is selected, MORICE uses `MORICE Projects/Quick Build` in your home folder.
3. Keep **Build or edit files** selected. Describe the files or changes in the composer and select **Build files**. For example: `Build a simple Python addition calculator`.
4. In the default folder-limited mode, open **Review**, inspect the proposed changes, then select **Save reviewed files**. Until that action, the proposal has not changed your source files. **Discard proposal** leaves the files unchanged.
5. Inspect actual saved files under **Files**, checks and errors under **Output**, and the conversation under **Updates**. A web project's existing browser appears under **Preview**. A build that cannot complete its checks remains visibly partial.

Choose **Ask about this project** to get an explanation without requesting file changes. Explicit instructions such as `Do not generate code` also keep the request on the explanation path. Opening **Chats** returns to ordinary chat.

**Build settings** contains access and online/local lookup controls. Existing Full access remains available; explicit denials and unsupported operations still apply. **Stop build** cancels the existing build token and its owned work. Already completed file changes remain available for inspection and undo. If browser verification needs attention, open **Preview**, complete any required browser interaction and use **Resume build**. That blocked check reports its status without asking the model to rewrite source.

The selected GGUF or Ollama model is reused by Builder. Leaving model selection empty uses the same available bundled/default model as chat. No weights are downloaded automatically. A missing model or invalid proposal produces a visible partial result rather than a claim that files were created.

## Run an experiment

1. Open **Research → New experiment**.
2. Describe a supported experiment with physical values and units, or choose **Choose a model and enter values**. The form supports driven oscillators, thermal expansion, ideal mixture density, and particles in vacuum. Inputs are required; MORICE does not invent material properties.
3. For a sweep, select **Parameter sweep**, choose the varying parameter, and enter the range and number of runs.
4. Select **Review experiment**. MORICE compiles the plan using the existing laboratory and shows its actual inputs, model limits, and planned run count.
5. Select **Run experiment**. Watch completed runs under **Experiments** and numerical outputs under **Results**. Pause, resume or cancel using the same workspace. Completed results remain in the existing experiment database.

The **Use an oscillator example** button inserts an explicitly labelled demonstration. It does not start a run. Missing inputs and unsupported domains are explained in Research, with the draft preserved. They do not fall back to a normal-chat code response.

**Notebooks** selects or creates a stored research project. **Advanced** exposes the existing JSON specification, diagnostics and evidence graph. Advanced specifications retain Monte Carlo, optimization and other existing compiler capabilities.

## Concrete limits

- Automatic source proposals retain the shared agent capability's 2,000-character task contract and bounded model output (up to 1,024 tokens for Project calls). Complete goals that fit are preserved ahead of optional repository excerpts. Oversized requests are reported as partial and remain stored; split them into smaller changes. This release does not claim arbitrary large application generation.
- Python, SDKs, editors, dependencies and external services must actually be installed for their corresponding checks. A source file is not a compiled executable. Unavailable checks remain unverified.
- Natural-language experiment compilation is conservative and limited to the four implemented models. General multiphysics, chemical compatibility, arbitrary material impact and external solvers are not integrated. These are simulations, not measured physical results.
- Preparation and start/pause/cancel commands use existing bounded UI workers. A background experiment runs through the existing laboratory dispatcher and shared agent/kernel authorities; a UI worker does not wait for the full experiment to finish.
- This update was verified with deterministic source generation, controlled model proposals, actual file execution and actual experiment runs. New real-weight inference validation remains constrained by the previously documented available-RAM limit (about 3.5 GiB available during this run). No additional model download or hardware certification is implied.

All routes remain accessible. New sessions show labelled primary navigation; additional tools live under **More**. Saved navigation choices are preserved, and compact windows can collapse the labels.
