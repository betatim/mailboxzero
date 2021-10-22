import { Controller } from "@hotwired/stimulus"

export default class extends Controller {
  static targets = [ "source", "notification" ]

  nextFrame() {
    return new Promise(resolve => window.requestAnimationFrame(() => resolve()));
  }

  async copy() {
    if (this.resetTimer) {
      clearTimeout(this.resetTimer)
    }
    navigator.clipboard.writeText(this.sourceTarget.textContent)

    this.notificationTarget.style.opacity = 1
    this.notificationTarget.style.visibility = "inherit"

    this.resetTimer = window.setTimeout(() => {
      this.reset()
    }, 5000)
  }

  reset() {
    this.notificationTarget.style.opacity = 0
    this.notificationTarget.style.visibility = "hidden"
  }

  disconnect() {
    this.reset()
    if (this.resetTimer) {
      clearTimeout(this.resetTimer)
    }
  }
}
