import React, { useState, useEffect } from 'react';
import { Lock, Check, Delete, X } from 'lucide-react';

export default function SalaryPinModal({ isOpen, onClose, onUnlocked }) {
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [shake, setShake] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setPin('');
      setError('');
      setShake(false);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;
      if (e.key >= '0' && e.key <= '9') {
        handleDigit(e.key);
      } else if (e.key === 'Backspace') {
        handleDelete();
      } else if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, pin]);

  if (!isOpen) return null;

  const handleDigit = (digit) => {
    if (pin.length >= 4) return;
    const nextPin = pin + String(digit);
    setPin(nextPin);
    setError('');

    if (nextPin.length === 4) {
      setTimeout(() => {
        const savedPin = localStorage.getItem('salary_pin_code') || '1234';
        if (nextPin === savedPin) {
          onUnlocked();
          onClose();
        } else {
          setError('Incorrect PIN. Please try again.');
          setShake(true);
          setPin('');
          setTimeout(() => setShake(false), 500);
        }
      }, 150);
    }
  };

  const handleDelete = () => {
    setPin((prev) => prev.slice(0, -1));
    setError('');
  };

  const handleClear = () => {
    setPin('');
    setError('');
  };

  return (
    <div className="react-modal-overlay" onClick={onClose}>
      <div
        className="react-modal-card"
        style={{
          width: '340px',
          padding: '24px',
          textAlign: 'center',
          animation: shake ? 'shake 0.4s' : undefined,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '12px' }}>
          <div
            style={{
              width: '52px',
              height: '52px',
              borderRadius: '14px',
              background: '#eff6ff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#2563eb',
            }}
          >
            <Lock size={26} />
          </div>
        </div>

        <h3 style={{ fontSize: '1.15rem', fontWeight: 800, marginBottom: '4px' }}>
          Salary Access Control
        </h3>
        <p style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '16px' }}>
          Enter 4-digit PIN to reveal salary columns
        </p>

        {/* PIN Dots */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '14px', marginBottom: '16px' }}>
          {[0, 1, 2, 3].map((idx) => (
            <div
              key={idx}
              style={{
                width: '14px',
                height: '14px',
                borderRadius: '50%',
                border: '2px solid #2563eb',
                background: idx < pin.length ? '#2563eb' : 'transparent',
                transition: 'all 0.15s ease',
              }}
            />
          ))}
        </div>

        {error && (
          <div style={{ color: '#e11d48', fontSize: '0.76rem', fontWeight: 700, marginBottom: '12px' }}>
            {error}
          </div>
        )}

        {/* Numpad */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '10px',
            marginBottom: '16px',
          }}
        >
          {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((num) => (
            <button
              key={num}
              onClick={() => handleDigit(num)}
              style={{
                padding: '12px 0',
                fontSize: '1.25rem',
                fontWeight: 700,
                borderRadius: '10px',
                border: '1px solid #e2e8f0',
                background: '#f8fafc',
                cursor: 'pointer',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => (e.target.style.background = '#e2e8f0')}
              onMouseLeave={(e) => (e.target.style.background = '#f8fafc')}
            >
              {num}
            </button>
          ))}
          <button
            onClick={handleClear}
            style={{
              padding: '12px 0',
              fontSize: '0.9rem',
              fontWeight: 700,
              borderRadius: '10px',
              border: '1px solid #e2e8f0',
              background: '#f1f5f9',
              color: '#64748b',
              cursor: 'pointer',
            }}
          >
            Clear
          </button>
          <button
            onClick={() => handleDigit(0)}
            style={{
              padding: '12px 0',
              fontSize: '1.25rem',
              fontWeight: 700,
              borderRadius: '10px',
              border: '1px solid #e2e8f0',
              background: '#f8fafc',
              cursor: 'pointer',
            }}
          >
            0
          </button>
          <button
            onClick={handleDelete}
            style={{
              padding: '12px 0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '10px',
              border: '1px solid #e2e8f0',
              background: '#f1f5f9',
              color: '#64748b',
              cursor: 'pointer',
            }}
          >
            <Delete size={20} />
          </button>
        </div>

        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: '#64748b',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
