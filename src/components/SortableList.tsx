import type { ReactNode } from 'react'
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import { restrictToParentElement, restrictToVerticalAxis } from '@dnd-kit/modifiers'
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { haptic } from '../lib/feedback'

/**
 * Vertikal sortierbare Liste. Gezogen wird ausschließlich am Griff
 * (`handleProps`), damit Eingabefelder in den Zeilen normal bedienbar bleiben.
 */
export function SortableList<T extends string>({
  items,
  onReorder,
  renderItem,
}: {
  items: T[]
  onReorder: (next: T[]) => void
  renderItem: (id: T, index: number, handleProps: HandleProps) => ReactNode
}) {
  const sensors = useSensors(
    // Erst nach kurzem Halten ziehen — sonst kollidiert es mit dem Scrollen.
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 8 } }),
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e
    if (!over || active.id === over.id) return
    const from = items.indexOf(active.id as T)
    const to = items.indexOf(over.id as T)
    if (from < 0 || to < 0) return
    haptic('tap')
    onReorder(arrayMove(items, from, to))
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={onDragEnd}
      onDragStart={() => haptic('tap')}
      modifiers={[restrictToVerticalAxis, restrictToParentElement]}
    >
      <SortableContext items={items} strategy={verticalListSortingStrategy}>
        {items.map((id, index) => (
          <SortableRow key={id} id={id}>
            {(handleProps) => renderItem(id, index, handleProps)}
          </SortableRow>
        ))}
      </SortableContext>
    </DndContext>
  )
}

export interface HandleProps {
  ref: (el: HTMLElement | null) => void
  listeners: Record<string, unknown>
  attributes: Record<string, unknown>
}

function SortableRow({ id, children }: { id: string; children: (h: HandleProps) => ReactNode }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id })

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        zIndex: isDragging ? 30 : undefined,
        opacity: isDragging ? 0.9 : 1,
        boxShadow: isDragging ? '0 12px 32px rgba(0,0,0,0.6)' : undefined,
        position: 'relative',
      }}
    >
      {children({
        ref: setActivatorNodeRef,
        listeners: (listeners ?? {}) as Record<string, unknown>,
        attributes: attributes as unknown as Record<string, unknown>,
      })}
    </div>
  )
}

/** Standard-Griff (⠿) für sortierbare Zeilen. */
export function DragHandle({ handleProps, className = '' }: { handleProps: HandleProps; className?: string }) {
  const { ref, listeners, attributes } = handleProps
  return (
    <button
      ref={ref as unknown as React.Ref<HTMLButtonElement>}
      {...attributes}
      {...listeners}
      aria-label="Verschieben"
      className={`shrink-0 cursor-grab touch-none px-2 py-2 text-mute active:cursor-grabbing ${className}`}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
        <circle cx="5" cy="3.5" r="1.4" />
        <circle cx="11" cy="3.5" r="1.4" />
        <circle cx="5" cy="8" r="1.4" />
        <circle cx="11" cy="8" r="1.4" />
        <circle cx="5" cy="12.5" r="1.4" />
        <circle cx="11" cy="12.5" r="1.4" />
      </svg>
    </button>
  )
}
