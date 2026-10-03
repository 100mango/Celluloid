import SwiftUI
import CelluloidDomain
import CelluloidRendering

struct SourceInspector: View {
    let recipe: EditRecipe
    let change: (EditRecipe, String) -> Void
    @State private var selected: UUID?
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Source Photos").font(.headline)
            ForEach(Array(recipe.sources.enumerated()), id: \.element.id) { index, source in
                VStack(alignment: .leading, spacing: 8) {
                    Button { selected = selected == source.id ? nil : source.id } label: {
                        HStack {
                            Text("\(index + 1). \(source.displayName)").lineLimit(1)
                            Spacer(); Image(systemName: selected == source.id ? "chevron.up" : "chevron.down")
                        }
                    }.buttonStyle(.plain)
                    if selected == source.id {
                        cropSlider("Horizontal crop", source, \.centerX, range: 0...1)
                        cropSlider("Vertical crop", source, \.centerY, range: 0...1)
                        cropSlider("Zoom", source, \.zoom, range: 1...5)
                        HStack {
                            Button("Reset Crop") { update(source.id, crop: SourceCrop()) }
                            Button("Earlier") { move(index, delta: -1) }.disabled(index == 0)
                            Button("Later") { move(index, delta: 1) }.disabled(index == recipe.sources.count - 1)
                        }
                        if recipe.sources.count > 1 {
                            Button("Remove Photo", role: .destructive) { remove(source.id) }
                        }
                    }
                }.padding(.vertical, 4)
            }
        }
    }
    private func cropSlider(_ label: String, _ source: SourceImage, _ path: WritableKeyPath<SourceCrop, Double>, range: ClosedRange<Double>) -> some View {
        VStack(alignment: .leading) {
            HStack { Text(LocalizedStringKey(label)); Spacer(); Text(source.crop[keyPath: path], format: .number.precision(.fractionLength(2))) }
            Slider(value: Binding(get: { source.crop[keyPath: path] }, set: { value in
                var crop = source.crop; crop[keyPath: path] = value; update(source.id, crop: crop)
            }), in: range).accessibilityLabel(String(format: NSLocalizedString("%@ for %@", comment: "Source crop accessibility"), NSLocalizedString(label, comment: "Crop control"), source.displayName))
        }
    }
    private func update(_ id: UUID, crop: SourceCrop) {
        guard let index = recipe.sources.firstIndex(where: { $0.id == id }) else { return }
        var next = recipe; next.sources[index].crop = crop; change(next, "Adjust Photo Crop")
    }
    private func move(_ index: Int, delta: Int) {
        let destination = index + delta
        guard recipe.sources.indices.contains(destination) else { return }
        var next = recipe; next.sources.swapAt(index, destination); change(next, "Reorder Photos")
    }
    private func remove(_ id: UUID) {
        var next = recipe; next.sources.removeAll { $0.id == id }
        if next.sources.count == 1, let source = next.sources.first {
            next.canvasWidth = source.pixelWidth; next.canvasHeight = source.pixelHeight; next.collageTemplate = nil
        } else {
            guard let name = try? NativeResources.templates(count: next.sources.count).first?.assetName else { return }
            next.collageTemplate = name
        }
        selected = nil; change(next, "Remove Photo")
    }
}
