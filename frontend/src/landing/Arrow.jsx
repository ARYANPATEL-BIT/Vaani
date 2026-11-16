/**
 * Arrow -- the small diagonal arrow on every "Start talking" link (nav,
 * hero, closing). Decorative: the link text already says where it goes.
 * Sized in em, so it scales with the text around it.
 */

export default function Arrow() {
  return (
    <svg className="lp-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 17L17 7M8 7h9v9" />
    </svg>
  );
}
