function run = load_run(runId, repoRoot)
%LOAD_RUN  Load a dbsspeech run record and its outputs into MATLAB.
%
%   run = load_run('20260903_141500_psd_by_condition')
%   run = load_run(runId, '/path/to/repo')
%
%   Returns a struct with:
%     .record   the run record (runs/<runId>.json), decoded
%     .config   the resolved config snapshot for that run, decoded from JSON
%     .tables   struct of tables read from the run's CSV/Parquet outputs
%     .figures  cellstr of figure paths
%
%   This is the interop boundary. Analyses are written once, in Python, and
%   their outputs are read from either language. Nothing is ported.
%
%   See docs/interop.md.

    if nargin < 2 || isempty(repoRoot)
        repoRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    end

    recordPath = fullfile(repoRoot, 'runs', [runId '.json']);
    if ~isfile(recordPath)
        error('load_run:notFound', 'No run record at %s', recordPath);
    end
    run.record = jsondecode(fileread(recordPath));

    outDir = fullfile(repoRoot, 'derivatives', 'results', runId);
    if ~isfolder(outDir)
        warning('load_run:noOutputs', ...
            'Run record found but outputs are missing at %s. derivatives/ is not committed; regenerate the run.', outDir);
        run.config  = struct();
        run.tables  = struct();
        run.figures = {};
        return
    end

    % Config snapshot is written as JSON precisely so MATLAB can read it
    % without a YAML parser.
    configPath = fullfile(outDir, 'config.json');
    if isfile(configPath)
        run.config = jsondecode(fileread(configPath));
    else
        run.config = struct();
    end

    run.tables = struct();
    for ext = {'*.csv', '*.parquet'}
        listing = dir(fullfile(outDir, ext{1}));
        for k = 1:numel(listing)
            [~, stem] = fileparts(listing(k).name);
            fieldName = matlab.lang.makeValidName(stem);
            full = fullfile(outDir, listing(k).name);
            if endsWith(listing(k).name, '.parquet')
                run.tables.(fieldName) = parquetread(full);
            else
                run.tables.(fieldName) = readtable(full);
            end
        end
    end

    figListing = [dir(fullfile(outDir, '*.png')); dir(fullfile(outDir, '*.svg'))];
    run.figures = fullfile({figListing.folder}, {figListing.name});

    if isfield(run.record, 'git_dirty') && run.record.git_dirty
        warning('load_run:dirtyTree', ...
            'Run %s was produced from a dirty working tree; the code that made it is not in any commit.', runId);
    end
end
