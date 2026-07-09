// components/Skeleton.tsx
interface Props { height?: number; width?: string; radius?: number }
export default function Skeleton({ height = 20, width = "100%", radius = 4 }: Props) {
  return <div className="skeleton" style={{ height: `${height}px`, width, borderRadius: `${radius}px` }}/>
}