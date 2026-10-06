/**
 * StateStepper — 5-step row of icon buttons driven by real pipeline turnState.
 *
 * States: idle | listening | thinking | speaking | cancelling
 * (maps cancelling → Interrupted visually)
 */

import { Circle, Mic, Brain, Volume2, XCircle } from 'lucide-react';
import './StateStepper.css';

const STEPS = [
  { id: 'idle',       label: 'Idle',        Icon: Circle   },
  { id: 'listening',  label: 'Listening',   Icon: Mic      },
  { id: 'thinking',   label: 'Thinking',    Icon: Brain    },
  { id: 'speaking',   label: 'Speaking',    Icon: Volume2  },
  { id: 'cancelling', label: 'Interrupted', Icon: XCircle  },
];

export default function StateStepper({ turnState = 'idle' }) {
  return (
    <div className="state-stepper" role="status" aria-label={`Current state: ${turnState}`}>
      {STEPS.map(({ id, label, Icon }) => {
        const isActive = turnState === id;
        return (
          <div key={id} className={`step-item${isActive ? ' active' : ''}`}>
            <div className="step-icon-wrap">
              <Icon size={20} strokeWidth={isActive ? 2 : 1.6} />
            </div>
            <span className="step-label">{label}</span>
          </div>
        );
      })}
    </div>
  );
}
