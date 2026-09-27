import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useCreateSampleContract, useUploadContract } from '../hooks/useContract';
import { useHealth } from '../hooks/useObligations';
import { useJob } from '../hooks/useJob';
import type { UploadResponse } from '../types/api';

const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

export const UploadPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const autoSampleStarted = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [contractId, setContractId] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const uploadMutation = useUploadContract();
  const sampleMutation = useCreateSampleContract();
  const { data: job, error: jobQueryError } = useJob(jobId ?? undefined);
  // Pre-warm: the free Render instance sleeps, so wake it while the user picks a file.
  useHealth();

  const isUploading = uploadMutation.isPending || sampleMutation.isPending;
  const isJobRunning = Boolean(
    jobId &&
    job &&
    (job.state === 'queued' || job.state === 'running')
  );
  const isBusy = isUploading || isJobRunning;

  // Handle terminal job states
  useEffect(() => {
    if (!job) return;

    if (job.state === 'done' || job.state === 'done_with_warnings') {
      const targetId = contractId || job.contract_id;
      if (targetId) {
        navigate(`/contracts/${targetId}`, {
          state: { warnings: job.warnings ?? [] },
        });
      }
    }
  }, [job, contractId, navigate]);

  const validateFile = (file: File): boolean => {
    setValidationError(null);
    setUploadError(null);

    const isPdf =
      file.type === 'application/pdf' ||
      file.name.toLowerCase().endsWith('.pdf');

    if (!isPdf) {
      setValidationError('Only PDF files are supported. Please select a valid .pdf contract.');
      return false;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      setValidationError(`File size (${sizeMb} MB) exceeds the 10 MB maximum limit.`);
      return false;
    }

    return true;
  };

  const handleFileSelect = (file: File) => {
    if (isBusy) return;

    if (validateFile(file)) {
      setSelectedFile(file);
    } else {
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (isBusy) return;

    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleSubmit = () => {
    if (!selectedFile || isBusy) return;

    if (!validateFile(selectedFile)) {
      return;
    }

    setUploadError(null);

    uploadMutation.mutate(selectedFile, {
      onSuccess: (data: UploadResponse) => {
        setContractId(data.contract_id);
        if (data.job_id) {
          setJobId(data.job_id);
        } else {
          // Cached or immediate analysis
          navigate(`/contracts/${data.contract_id}`);
        }
      },
      onError: (err: Error) => {
        setUploadError(err.message || 'Failed to upload contract. Please try again.');
      },
    });
  };

  const handleTrySample = () => {
    if (isBusy) return;
    setValidationError(null);
    setUploadError(null);
    sampleMutation.mutate(undefined, {
      onSuccess: (data: UploadResponse) => {
        setContractId(data.contract_id);
        if (data.job_id) {
          setJobId(data.job_id);
        } else {
          navigate(`/contracts/${data.contract_id}`);
        }
      },
      onError: (err: Error) => {
        const reason = (err.message || 'Could not load the sample contract.').replace(/\.?$/, '.');
        setUploadError(`${reason} The offline demo below still works without the server.`);
      },
    });
  };

  // Landing page "Try Sample Contract" links here with ?sample=1: start the sample straight away.
  useEffect(() => {
    if (searchParams.get('sample') !== '1' || autoSampleStarted.current) return;
    autoSampleStarted.current = true;
    setSearchParams({}, { replace: true });
    handleTrySample();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleReset = () => {
    setSelectedFile(null);
    setValidationError(null);
    setUploadError(null);
    setContractId(null);
    setJobId(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="flex-1 max-w-3xl mx-auto w-full px-4 sm:px-6 py-12 sm:py-16">
      {/* Page Heading */}
      <div className="text-center space-y-2 mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
          Upload Contract
        </h1>
        <p className="text-sm text-slate-400 font-mono">
          PDF only • Maximum 10 MB • Maximum 30 pages
        </p>
      </div>

      {/* Validation Error Banner */}
      {validationError && (
        <div className="mb-6 p-4 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-200 text-sm flex items-start space-x-3">
          <svg className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div className="flex-1">
            <p className="font-medium text-rose-100">Invalid File</p>
            <p className="text-xs text-rose-300 mt-0.5">{validationError}</p>
          </div>
        </div>
      )}

      {/* Upload Mutation Error Banner */}
      {uploadError && (
        <div className="mb-6 p-4 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-200 text-sm flex items-start space-x-3">
          <svg className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="flex-1">
            <p className="font-medium text-rose-100">Upload Failed</p>
            <p className="text-xs text-rose-300 mt-0.5">{uploadError}</p>
          </div>
        </div>
      )}

      {/* Job Failed Error State */}
      {job && job.state === 'failed' && (
        <div className="mb-6 p-5 rounded-lg bg-rose-950/50 border border-rose-700 text-rose-200 space-y-3">
          <div className="flex items-start space-x-3">
            <svg className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div className="flex-1 space-y-1">
              <div className="flex items-center space-x-2">
                <span className="font-semibold text-white">Processing Failed</span>
                {job.error_code && (
                  <span className="px-2 py-0.5 text-xs font-mono rounded bg-rose-900 border border-rose-700 text-rose-200">
                    {job.error_code}
                  </span>
                )}
              </div>
              <p className="text-xs text-rose-200">
                {job.error_message || job.message || 'An error occurred while processing the contract.'}
              </p>
              {job.error_action && (
                <p className="text-xs text-slate-300 pt-1">
                  <strong className="text-white">Recommendation:</strong> {job.error_action}
                </p>
              )}
            </div>
          </div>

          <div className="pt-2 border-t border-rose-900/60 flex justify-end">
            <button
              type="button"
              onClick={handleReset}
              className="px-3.5 py-1.5 rounded bg-rose-900/60 hover:bg-rose-900 text-xs font-medium text-white transition-colors"
            >
              Try Another Contract
            </button>
          </div>
        </div>
      )}

      {/* Query Error when Polling Job */}
      {jobQueryError && (
        <div className="mb-6 p-4 rounded-lg bg-amber-950/40 border border-amber-800 text-amber-200 text-sm">
          <p className="font-medium text-amber-100">Job Status Check Failed</p>
          <p className="text-xs text-amber-300 mt-0.5">{jobQueryError.message}</p>
        </div>
      )}

      {/* Active Processing State Display */}
      {isJobRunning && job && (
        <div className="mb-8 p-6 rounded-xl border border-slate-700 bg-slate-900/80 space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
                Pipeline Status
              </span>
              <h2 className="text-sm font-semibold text-white capitalize">
                {job.stage ? job.stage.replace(/_/g, ' ') : 'Analyzing contract...'}
              </h2>
            </div>
            <span className="px-2.5 py-1 text-xs font-mono font-medium rounded bg-slate-800 text-slate-300 border border-slate-700 uppercase">
              {job.state}
            </span>
          </div>

          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs font-mono text-slate-400">
              <span>
                {job.stage_count > 0
                  ? `Stage ${job.stage_index + 1} of ${job.stage_count}`
                  : 'Processing'}
              </span>
              <span>{job.progress_pct}%</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-slate-300 h-2 rounded-full transition-all duration-300"
                style={{ width: `${Math.max(5, Math.min(100, job.progress_pct))}%` }}
              />
            </div>
          </div>

          {/* Progress Message */}
          {job.message && (
            <p className="text-xs text-slate-400 font-mono">
              {job.message}
            </p>
          )}

          {/* Warnings list if any */}
          {job.warnings && job.warnings.length > 0 && (
            <div className="p-3 rounded bg-amber-950/30 border border-amber-900/60 text-xs text-amber-300 space-y-1">
              <span className="font-semibold block text-amber-200">Warnings:</span>
              <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                {job.warnings.map((w: string, idx: number) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Uploading Spinner */}
      {isUploading && (
        <div className="mb-8 p-6 rounded-xl border border-slate-700 bg-slate-900/80 text-center space-y-2">
          <div className="inline-block w-6 h-6 border-2 border-slate-400 border-t-white rounded-full animate-spin" />
          <p className="text-sm font-medium text-white">
            {sampleMutation.isPending ? 'Loading sample contract...' : 'Uploading contract...'}
          </p>
          <p className="text-xs text-slate-400">
            {sampleMutation.isPending ? 'The first request can take up to a minute while the server wakes' : 'Streaming document to server'}
          </p>
        </div>
      )}

      {/* PDF Drop / Upload Zone (Hidden while processing or failed) */}
      {!isBusy && (!job || job.state !== 'failed') && (
        <div className="space-y-6">
          <div
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-xl p-8 sm:p-12 text-center transition-colors ${
              selectedFile
                ? 'border-slate-600 bg-slate-900/60'
                : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
            }`}
          >
            <input
              type="file"
              id="contract-upload"
              ref={fileInputRef}
              accept=".pdf,application/pdf"
              onChange={handleInputChange}
              disabled={isBusy}
              className="hidden"
            />

            <label
              htmlFor="contract-upload"
              className="cursor-pointer flex flex-col items-center justify-center space-y-4"
            >
              <div className="w-12 h-12 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
                <svg
                  className="w-6 h-6"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                  />
                </svg>
              </div>

              <div className="space-y-1">
                <p className="text-sm font-medium text-slate-200">
                  Drag and drop your contract PDF here, or{' '}
                  <span className="text-slate-100 underline decoration-slate-600 underline-offset-4 hover:decoration-slate-400">
                    browse files
                  </span>
                </p>
                <p className="text-xs text-slate-500">
                  Standard contract agreements, master services agreements, or schedules
                </p>
              </div>

              {selectedFile && (
                <div className="mt-4 px-3 py-1.5 rounded-md bg-slate-800 border border-slate-700 text-xs text-slate-200 font-mono flex items-center space-x-2">
                  <span>Selected: {selectedFile.name}</span>
                  <span className="text-slate-400">
                    ({(selectedFile.size / (1024 * 1024)).toFixed(2)} MB)
                  </span>
                </div>
              )}
            </label>
          </div>

          {/* Upload Button */}
          {selectedFile && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSubmit}
                disabled={isBusy}
                className="px-5 py-2.5 rounded-md bg-slate-100 hover:bg-white text-slate-950 font-semibold text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Upload and Analyze
              </button>
            </div>
          )}
        </div>
      )}

      {/* Alternative Sample Action */}
      <div className="mt-8 pt-8 border-t border-slate-850 flex flex-col sm:flex-row items-center justify-between gap-4">
        <span className="text-xs text-slate-500">
          Want to test the workflow without uploading your own document?
        </span>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleTrySample}
            disabled={isBusy}
            className="px-4 py-2 rounded-md bg-slate-900 hover:bg-slate-800 border border-slate-800 text-xs font-medium text-slate-300 hover:text-white transition-colors text-center whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Try Sample Contract
          </button>
          <Link
            to="/contracts/demo?offline=1"
            className="px-3 py-2 text-xs font-medium text-slate-500 hover:text-slate-300 transition-colors whitespace-nowrap"
          >
            Offline demo
          </Link>
        </div>
      </div>

      <p className="mt-6 text-[11px] text-slate-500 text-center">
        Conan is an operations aid, not legal advice. Use only fictional or public contracts: free-tier AI inputs may be used by the provider.
      </p>
    </div>
  );
};
