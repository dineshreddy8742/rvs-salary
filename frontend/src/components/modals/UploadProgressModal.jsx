import React from 'react';
import { Cloud, CheckCircle, AlertTriangle } from 'lucide-react';

export default function UploadProgressModal({
  isOpen,
  fileName,
  fileSize,
  progress,
  status, // 'uploading' | 'processing' | 'success' | 'error'
  message,
  detectedMonth,
  onClose,
}) {
  if (!isOpen) return null;

  const isSuccess = status === 'success';
  const isError = status === 'error';

  return (
    <div className="react-modal-overlay">
      <div
        className="react-modal-card"
        style={{
          width: '480px',
          maxWidth: '92vw',
          padding: '24px 28px',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '18px' }}>
          <div
            style={{
              width: '52px',
              height: '52px',
              borderRadius: '14px',
              background: isSuccess
                ? 'linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)'
                : isError
                ? 'linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%)'
                : 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '26px',
              color: isSuccess ? '#10b981' : isError ? '#ef4444' : '#2563eb',
            }}
          >
            {isSuccess ? (
              <CheckCircle size={28} />
            ) : isError ? (
              <AlertTriangle size={28} />
            ) : (
              <Cloud size={28} />
            )}
          </div>
          <div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 800, margin: '0 0 2px 0' }}>
              {isSuccess
                ? 'Attendance Imported Successfully!'
                : isError
                ? 'Upload Processing Failed'
                : 'Uploading Biometric Dump'}
            </h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
              {fileName} {fileSize ? `(${fileSize})` : ''}
            </p>
          </div>
        </div>

        {/* Progress & Bar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                padding: '3px 10px',
                borderRadius: '20px',
                background: isSuccess ? '#ecfdf5' : isError ? '#fef2f2' : '#eff6ff',
                color: isSuccess ? '#059669' : isError ? '#dc2626' : '#2563eb',
                border: `1px solid ${isSuccess ? '#a7f3d0' : isError ? '#fecaca' : '#bfdbfe'}`,
              }}
            >
              {isSuccess ? 'Completed' : isError ? 'Failed' : 'Processing'}
            </span>
            <span style={{ fontSize: '1.25rem', fontWeight: 900, color: '#0f172a' }}>
              {Math.round(progress)}%
            </span>
          </div>

          <div
            style={{
              width: '100%',
              height: '10px',
              borderRadius: '999px',
              background: '#e2e8f0',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${Math.min(100, Math.max(0, progress))}%`,
                height: '100%',
                background: isSuccess
                  ? 'linear-gradient(90deg, #10b981 0%, #059669 100%)'
                  : isError
                  ? 'linear-gradient(90deg, #ef4444 0%, #dc2626 100%)'
                  : 'linear-gradient(90deg, #3b82f6 0%, #2563eb 50%, #4f46e5 100%)',
                transition: 'width 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
              }}
            />
          </div>

          <div style={{ fontSize: '0.82rem', color: '#475569', minHeight: '20px' }}>
            {message || 'Reading biometric machine punch records...'}
          </div>

          {detectedMonth && (
            <div
              style={{
                background: '#f8fafc',
                border: '1px solid #cbd5e1',
                borderRadius: '8px',
                padding: '6px 12px',
                fontSize: '0.78rem',
                color: '#334155',
                marginTop: '4px',
              }}
            >
              📅 Detected Month: <strong>{detectedMonth}</strong> (from biometric punch timestamps)
            </div>
          )}
        </div>

        {isError && (
          <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={onClose}
              style={{
                padding: '7px 16px',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                background: 'white',
                fontSize: '0.82rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Dismiss
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
