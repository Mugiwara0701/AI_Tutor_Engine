// src/features/auth/components/AuthBackgroundArt.jsx
//
// Decorative background illustration for the auth page: a flowing
// network of curved lines and points, bottom-left, on a near-black
// backdrop. Purely decorative — aria-hidden, no interaction.

export default function AuthBackgroundArt() {
  return (
    <svg
      className="absolute bottom-0 left-0 w-[52%] max-w-[820px] h-auto opacity-70 pointer-events-none select-none"
      viewBox="0 0 800 700"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient
          id="wave1"
          x1="0"
          y1="700"
          x2="800"
          y2="200"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
        </linearGradient>
        <linearGradient
          id="wave2"
          x1="0"
          y1="700"
          x2="700"
          y2="120"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#2563EB" stopOpacity="0.45" />
          <stop offset="100%" stopColor="#2563EB" stopOpacity="0" />
        </linearGradient>
        <linearGradient
          id="wave3"
          x1="0"
          y1="650"
          x2="600"
          y2="50"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#7dd3fc" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#7dd3fc" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Flowing wave lines */}
      <path
        d="M-40 640 C 120 560, 180 480, 140 400 S 60 260, 180 180 S 400 100, 360 -20"
        stroke="url(#wave1)"
        strokeWidth="1.2"
      />
      <path
        d="M-40 660 C 140 600, 200 520, 160 440 S 100 300, 220 220 S 440 140, 400 0"
        stroke="url(#wave2)"
        strokeWidth="1"
      />
      <path
        d="M-40 600 C 100 540, 140 460, 100 380 S 20 240, 140 160 S 340 60, 300 -40"
        stroke="url(#wave3)"
        strokeWidth="0.8"
      />
      <path
        d="M-40 700 C 180 640, 260 540, 200 460 S 100 320, 260 240 S 520 160, 460 20"
        stroke="url(#wave1)"
        strokeWidth="0.6"
      />
      <path
        d="M-40 500 C 60 460, 90 400, 60 340 S 0 240, 90 180 S 240 100, 210 10"
        stroke="url(#wave2)"
        strokeWidth="0.6"
      />

      {/* Scattered node points */}
      {[
        [40, 610],
        [110, 555],
        [160, 470],
        [130, 400],
        [70, 330],
        [190, 260],
        [240, 190],
        [180, 120],
        [300, 70],
        [340, 10],
        [60, 460],
        [20, 380],
        [90, 240],
        [150, 60],
        [260, 340],
      ].map(([cx, cy], i) => (
        <circle
          key={i}
          cx={cx}
          cy={cy}
          r={i % 4 === 0 ? 2.4 : 1.4}
          fill="#7dd3fc"
          opacity={i % 3 === 0 ? 0.8 : 0.4}
        />
      ))}
    </svg>
  );
}
