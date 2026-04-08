interface Props {
  height?: number
  width?:  string
  radius?: number
}

export default function Skeleton({ height = 20, width = "100%", radius = 6 }: Props) {
  return (
    <div style={{
      height: `${height}px`,
      width,
      background: "#1e293b",
      borderRadius: `${radius}px`,
      animation: "skeleton-pulse 1.5s ease-in-out infinite"
    }}>
      <style>{`
        @keyframes skeleton-pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.4; }
        }
      `}</style>
    </div>
  )
}