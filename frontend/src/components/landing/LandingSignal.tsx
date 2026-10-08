// Deterministic SVG keeps the halftone visible without WebGL or image assets.
const dots: {
  x: number;
  y: number;
  radius: number;
  opacity: number;
  orange: boolean;
}[] = [];
for (let x = 0; x <= 1680; x += 11) {
  for (let y = 0; y <= 620; y += 11) {
    const left = x < 180;
    if (!left && x < 620) continue;
    const center = left
      ? 140 + x * 1.7
      : 378 - 140 * Math.tanh((x - 1000) / 230);
    const distance = y - center;
    const strength = Math.exp(-((distance / (left ? 90 : 76)) ** 2));
    const fade = left
      ? Math.max(0, 1 - x / 180)
      : Math.min(1, (x - 620) / 190) * Math.min(1, (1720 - x) / 320);
    const intensity = strength * fade;
    if (intensity < 0.035) continue;
    dots.push({
      x,
      y,
      radius: 0.7 + intensity * 3.4,
      opacity: intensity * 0.78,
      orange: distance > 12 && distance < 58,
    });
  }
}

export function LandingSignal() {
  return (
    <div className="landing-signal" aria-hidden="true">
      <svg
        viewBox="0 0 1680 620"
        preserveAspectRatio="xMidYMid slice"
        focusable="false"
      >
        {dots.map(({ x, y, radius, opacity, orange }) => (
          <circle
            key={`${x}-${y}`}
            cx={x}
            cy={y}
            r={radius}
            fill={orange ? "#ffb774" : "#83b6ed"}
            opacity={opacity}
          />
        ))}
      </svg>
    </div>
  );
}
