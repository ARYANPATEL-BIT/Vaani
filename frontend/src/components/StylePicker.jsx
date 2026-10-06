/**
 * StylePicker — "Conversation style" card in the right panel.
 *
 * Maps to real backend personas (default / tutor / support).
 * Only labels/descriptions change; the underlying persona IDs are preserved.
 */

import { GraduationCap, Smile, Heart } from 'lucide-react';
import './StylePicker.css';

const STYLE_OPTIONS = [
  {
    id: 'tutor',
    icon: GraduationCap,
    label: 'Teacher',
    desc: 'Explains clearly, structured',
  },
  {
    id: 'default',
    icon: Smile,
    label: 'Friend',
    desc: 'Casual, natural conversation',
  },
  {
    id: 'support',
    icon: Heart,
    label: 'Companion',
    desc: 'Thoughtful, concise, supportive',
  },
];

export default function StylePicker({ value, onChange, disabled }) {
  return (
    <div className="style-picker-card glass-card">
      <h3 className="card-title">Conversation style</h3>
      <div className="style-options">
        {STYLE_OPTIONS.map(({ id, icon: Icon, label, desc }) => {
          const isSelected = value === id;
          return (
            <button
              key={id}
              className={`style-option${isSelected ? ' selected' : ''}`}
              onClick={() => !disabled && onChange(id)}
              disabled={disabled}
              aria-pressed={isSelected}
              title={disabled ? 'Cannot change while session is active' : `Select ${label}`}
            >
              <div className="style-icon-wrap">
                <Icon size={18} strokeWidth={1.8} />
              </div>
              <div className="style-text">
                <span className="style-label">{label}</span>
                <span className="style-desc">{desc}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
