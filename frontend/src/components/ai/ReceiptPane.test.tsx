/**
 * The compact receipt — what a phone shows in place of the pane, so the
 * review form keeps the screen. One tap must still reach the whole receipt.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const url = vi.hoisted(() => ({ value: 'blob:receipt' as string | undefined }))

vi.mock('../../api/attachments', () => ({
  useAttachmentUrl: () => ({ data: url.value }),
}))
vi.mock('../attachments/Lightbox', () => ({
  Lightbox: ({ src }: { src: string }) => <div data-testid="lightbox" data-src={src} />,
}))

import { ReceiptPane } from './ReceiptPane'

afterEach(() => {
  url.value = 'blob:receipt'
  vi.restoreAllMocks()
})

describe('ReceiptPane compact', () => {
  it('draws a button, not the image', () => {
    render(<ReceiptPane attachmentId="att-1" contentType="image/jpeg" compact />)
    expect(screen.getByRole('button', { name: 'View receipt' })).toBeInTheDocument()
    expect(screen.queryByRole('img')).toBeNull()
  })

  it('opens the full-screen viewer on a tap', () => {
    render(<ReceiptPane attachmentId="att-1" contentType="image/jpeg" compact />)
    fireEvent.click(screen.getByRole('button', { name: 'View receipt' }))
    expect(screen.getByTestId('lightbox')).toHaveAttribute('data-src', 'blob:receipt')
  })

  it('opens a PDF in its own tab, which the viewer cannot draw', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    render(<ReceiptPane attachmentId="att-1" contentType="application/pdf" compact />)
    fireEvent.click(screen.getByRole('button', { name: /View receipt/ }))
    expect(open).toHaveBeenCalledWith('blob:receipt', '_blank')
    expect(screen.queryByTestId('lightbox')).toBeNull()
  })

  it('waits, disabled, until the receipt has loaded', () => {
    url.value = undefined
    render(<ReceiptPane attachmentId="att-1" compact />)
    expect(screen.getByRole('button', { name: /Loading receipt/ })).toBeDisabled()
  })
})
