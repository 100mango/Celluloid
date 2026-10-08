import SwiftUI
import CelluloidDomain
import CelluloidRendering

struct SourceInspector: View {
    let recipe: EditRecipe
    let change: RecipeChange
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
                            Button("Reset Crop") { update(source.id) { $0 = SourceCrop() } }
                            Button("Earlier") { move(source.id, delta: -1) }.disabled(index == 0)
                            Button("Later") { move(source.id, delta: 1) }.disabled(index == recipe.sources.count - 1)
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
            HStack { Text(LocalizedStringKey(label)).editorAdjustmentLabel(); Spacer(); Text(source.crop[keyPath: path], format: .number.precision(.fractionLength(2))) }
            EditorSlider(value: Binding(get: { source.crop[keyPath: path] }, set: { value in
                update(source.id) { $0[keyPath: path] = value }
            }), range: range, label: String(format: NSLocalizedString("%@ for %@", comment: "Source crop accessibility"), NSLocalizedString(label, comment: "Crop control"), source.displayName))
        }
    }
    private func update(_ id: UUID, mutation: @escaping (inout SourceCrop) -> Void) {
        change({ $0.editSourceCrop(id, mutation: mutation) }, "Adjust Photo Crop")
    }
    private func move(_ id: UUID, delta: Int) {
        change({ current in
            guard let index = current.sources.firstIndex(where: { $0.id == id }),
                  current.sources.indices.contains(index + delta) else { return }
            current.sources.swapAt(index, index + delta)
        }, "Reorder Photos")
    }
    private func remove(_ id: UUID) {
        selected = nil
        change({ current in
            var next = current
            next.sources.removeAll { $0.id == id }
            if next.sources.count == 1, let source = next.sources.first {
                next.canvasWidth = source.pixelWidth; next.canvasHeight = source.pixelHeight; next.collageTemplate = nil
            } else {
                guard let name = try? NativeResources.templates(count: next.sources.count).first?.assetName else { return }
                next.collageTemplate = name
            }
            current = next
        }, "Remove Photo")
    }
}
