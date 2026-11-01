import * as echarts from 'echarts'
import { useEffect, useRef } from 'react'

// Thin ECharts wrapper: re-renders on option change, resizes with its container.
export default function EChart({ option, height = 220, onClick }: { option: echarts.EChartsOption; height?: number | string; onClick?: (p: echarts.ECElementEvent) => void }) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const currentOption = useRef(option)

  const apply = () => {
    const css = getComputedStyle(document.documentElement)
    const text = css.getPropertyValue('--muted').trim()
    const line = css.getPropertyValue('--line').trim()
    const axis = { axisLabel: { color: text, fontFamily: 'IBM Plex Sans', fontSize: 10 }, axisLine: { lineStyle: { color: line } }, splitLine: { lineStyle: { color: line, opacity: 0.5 } } }
    const themedAxis = (value: echarts.EChartsOption['xAxis'] | echarts.EChartsOption['yAxis']) => Array.isArray(value) ? value.map((a) => ({ ...axis, ...a, axisLabel: { ...axis.axisLabel, ...a.axisLabel } })) : value ? { ...axis, ...value, axisLabel: { ...axis.axisLabel, ...value.axisLabel } } : undefined
    chart.current?.setOption({ ...currentOption.current, backgroundColor: 'transparent', textStyle: { fontFamily: 'IBM Plex Sans', color: text }, xAxis: themedAxis(currentOption.current.xAxis), yAxis: themedAxis(currentOption.current.yAxis) }, true)
  }

  useEffect(() => {
    if (!el.current) return
    chart.current = echarts.init(el.current, document.documentElement.dataset.theme === 'light' ? undefined : 'dark', { renderer: 'canvas' })
    const ro = new ResizeObserver(() => chart.current?.resize())
    ro.observe(el.current)
    const theme = new MutationObserver(() => apply())
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => {
      ro.disconnect()
      theme.disconnect()
      chart.current?.dispose()
      chart.current = null
    }
  }, [])

  useEffect(() => {
    currentOption.current = option
    apply()
  }, [option])

  useEffect(() => {
    const c = chart.current
    if (!c || !onClick) return
    c.on('click', onClick)
    return () => {
      c.off('click', onClick)
    }
  }, [onClick])

  return <div ref={el} style={{ width: '100%', height }} />
}
