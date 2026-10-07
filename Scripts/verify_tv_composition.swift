import Foundation
import CoreGraphics
import ImageIO
import CryptoKit

// Independent verification of UI intent, actual persisted recipe, PhotoKit input
// identities, crop/order geometry, and actual PhotoKit-refetched output. No app
// renderer, recipe decoder or proof helper is imported into this executable.
func require(_ value: @autoclosure () -> Bool, _ reason:String) throws {
    if !value() { throw NSError(domain:"TVCompositionOracle",code:1,userInfo:[NSLocalizedDescriptionKey:reason]) }
}
func json(_ url:URL) throws -> [String:Any] {
    let size = try url.resourceValues(forKeys:[.fileSizeKey]).fileSize ?? Int.max
    try require(size<200_000,"Metadata limit")
    return try JSONSerialization.jsonObject(with:Data(contentsOf:url)) as! [String:Any]
}
func pairs(_ value:Any) -> [String:String] {
    if let dictionary = value as? [String:String] { return dictionary }
    let array = value as! [String];var result:[String:String]=[:]
    for i in stride(from:0,to:array.count,by:2) { result[array[i]]=array[i+1] };return result
}
struct Raster {
    let width:Int,height:Int,bytes:[UInt8]
    init(_ url:URL) throws {
        let size=try url.resourceValues(forKeys:[.fileSizeKey]).fileSize ?? Int.max
        try require(size<=5_000_000,"Image proof byte preflight")
        let data=try Data(contentsOf:url)
        try require(data.count<=5_000_000,"Image proof byte limit")
        guard let source=CGImageSourceCreateWithData(data as CFData,nil),let image=CGImageSourceCreateImageAtIndex(source,0,nil),let space=CGColorSpace(name:CGColorSpace.sRGB),
              image.width*image.height<=2_000_000,
              let context=CGContext(data:nil,width:image.width,height:image.height,bitsPerComponent:8,bytesPerRow:image.width*4,space:space,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue|CGBitmapInfo.byteOrder32Big.rawValue) else {throw NSError(domain:"TVCompositionOracle",code:2)}
        let w=image.width,h=image.height
        context.draw(image,in:CGRect(x:0,y:0,width:w,height:h))
        let samples=Array(UnsafeBufferPointer(start:context.data!.assumingMemoryBound(to:UInt8.self),count:w*h*4))
        width=w;height=h;bytes=samples
    }
    func pixel(_ x:Int,_ y:Int,flipped:Bool)->[UInt8] { let row=flipped ? height-1-y:y;let i=(row*width+x)*4;return Array(bytes[i..<i+4]) }
}
func delta(_ a:[UInt8],_ b:[UInt8])->Int {zip(a,b).map {abs(Int($0)-Int($1))}.max() ?? 0}
func distance(_ p:CGPoint,_ a:CGPoint,_ b:CGPoint)->Double {
    let dx=b.x-a.x,dy=b.y-a.y,denominator=dx*dx+dy*dy
    let t=denominator==0 ? 0:max(0,min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/denominator))
    return hypot(p.x-a.x-t*dx,p.y-a.y-t*dy)
}
func inside(_ point:CGPoint,_ polygon:[CGPoint])->Bool {
    var result=false,j=polygon.count-1
    for i in polygon.indices {
        let a=polygon[i],b=polygon[j]
        if (a.y>point.y) != (b.y>point.y), point.x<(b.x-a.x)*(point.y-a.y)/(b.y-a.y)+a.x {result.toggle()};j=i
    };return result
}
let temp=URL(fileURLWithPath:CommandLine.arguments[1]),root=URL(fileURLWithPath:CommandLine.arguments[2])
let lines=try String(contentsOfFile:CommandLine.arguments[3],encoding:.utf8).split(separator:"\n")
let expectedRows=try lines.filter {$0.hasPrefix("TV_NATIVE_COMPOSITION_EXPECTED ")}.map {try JSONSerialization.jsonObject(with:Data($0.dropFirst("TV_NATIVE_COMPOSITION_EXPECTED ".count).utf8)) as! [String:Any]}
let focused=CommandLine.arguments.count==6 && CommandLine.arguments[5]=="two-source-only"
let remainingRich=CommandLine.arguments.count==6 && CommandLine.arguments[5]=="remaining-rich"
try require(CommandLine.arguments.count==5 || focused || remainingRich,"Unknown composition verification scope")
try require(expectedRows.count==(focused ? 1:remainingRich ? 2:3),"Exact completed UI case count required for this fixed scope")
let templates=try json(URL(fileURLWithPath:CommandLine.arguments[4]))
let calibration=try Raster(temp.appendingPathComponent("CelluloidSource-1.png"))
let top=calibration.pixel(0,0,flipped:false),flipped=top != [9,19,29,255]
try require(calibration.pixel(0,0,flipped:flipped)==[9,19,29,255] && calibration.pixel(0,calibration.height-1,flipped:flipped)==[201,211,221,255],"Independent PNG row-order calibration")
var seen=Set<Int>(),outputs=Set<String>()
for expected in expectedRows {
    let count=expected["count"] as! Int
    if focused { try require(count==2 && expected["keyboardExercised"] as? Bool==true && expected["bubbleText"] as? String=="TV","The focused case requires actual system keyboard ASCII input, not Hello or a compile probe") }
    if remainingRich { try require([3,4].contains(count) && expected["keyboardExercised"] as? Bool==true && expected["bubbleText"] as? String=="TV 世界","Both remaining rich cases require actual full Unicode keyboard input") }
    try require((2...4).contains(count) && seen.insert(count).inserted,"Distinct 2/3/4 UI coverage")
    let folder=root.appendingPathComponent(String(count)),saved=try json(folder.appendingPathComponent("kept-recipe.json"))
    let recipe=saved["recipe"] as! [String:Any],sources=recipe["sources"] as! [[String:Any]],overlays=recipe["overlays"] as! [[String:Any]]
    var intended=expected["initialSources"] as! [[String:String]];let croppedAsset=intended[0]["assetID"]!;intended.swapAt(0,1)
    let ids=pairs(saved["photoIDs"]!),hashes=pairs(saved["fingerprints"]!)
    try require(sources.count==count && ids.count==count && hashes.count==count,"Exact source count")
    try require(recipe["collageTemplate"] as? String==expected["template"] as? String,"Chosen layout persisted")
    try require(recipe["filter"] as? String=="Original","Composition test must not inherit previous filtered output")
    var images:[Raster]=[],crops:[[String:Double]]=[]
    for (index,source) in sources.enumerated() {
        let id=source["id"] as! String;try require(UUID(uuidString:id) != nil,"Source UUID")
        try require(ids[id]==intended[index]["assetID"],"UI selection/order did not reach persisted recipe")
        let file=folder.appendingPathComponent(id+".image"),data=try Data(contentsOf:file)
        let hash=SHA256.hash(data:data).map {String(format:"%02x",$0)}.joined()
        try require(hashes[id]==hash,"Persisted fingerprint must bind actual PhotoKit source bytes")
        let actual=try Raster(file),seed=try Raster(temp.appendingPathComponent(intended[index]["filename"]!))
        try require(actual.width==seed.width && actual.height==seed.height && delta(actual.bytes,seed.bytes)==0,"An exported or different PHAsset substituted for the intended synthetic source")
        let crop=source["crop"] as! [String:Double],changed=ids[id]==croppedAsset
        try require(abs(crop["zoom"]!-(changed ? 1.5:1))<1e-9 && abs(crop["centerX"]!-(changed ? 0.45:0.5))<1e-9 && abs(crop["centerY"]!-(changed ? 0.55:0.5))<1e-9,"Pan/zoom did not travel with the reordered source")
        images.append(actual);crops.append(crop)
    }
    try require(overlays.count==2,"Both sticker and bubble must survive reopen")
    let sticker=overlays.first {$0["kind"] as? String=="sticker"}!,bubble=overlays.first {$0["kind"] as? String=="bubble"}!
    try require(sticker["asset"] as? String=="32" && sticker["mirrored"] as? Bool==true && abs((sticker["centerX"] as! Double)-0.26)<1e-9,"Sticker transform binding")
    try require(bubble["asset"] as? String=="say1" && bubble["text"] as? String==expected["bubbleText"] as? String && bubble["rotation"] as? Double==0,"Bubble text and actual Undo must survive reopen")
    let result=try json(folder.appendingPathComponent("photos-output.json")),outputURL=folder.appendingPathComponent("photos-output.png"),output=try Raster(outputURL)
    let outputID=result["assetIdentifier"] as! String;try require(outputs.insert(outputID).inserted && !ids.values.contains(outputID),"Export must be a new Photos asset")
    let digest=SHA256.hash(data:try Data(contentsOf:outputURL)).map {String(format:"%02x",$0)}.joined()
    try require(result["sha256"] as? String==digest && output.width==800 && output.height==800,"Actual Photos output proof")
    let group=templates[count==2 ? "two_pic":count==3 ? "three_pic":"four_pic"] as! [[String:Any]]
    let shape=group.first {$0["drawable_name"] as? String==expected["template"] as? String}!
    let polygons=(shape["polygons"] as! [[Double]]).map { raw in stride(from:0,to:raw.count,by:2).map {CGPoint(x:raw[$0]*8,y:raw[$0+1]*8)} }
    let boxes=overlays.map { layer in CGRect(x:((layer["centerX"] as! Double)-(layer["width"] as! Double)/2)*800,y:((layer["centerY"] as! Double)-(layer["height"] as! Double)/2)*800,width:(layer["width"] as! Double)*800,height:(layer["height"] as! Double)*800) }
    var verified=[Int](repeating:0,count:count),changed=[Int](repeating:0,count:2),maximum=0
    for y in stride(from:16,to:784,by:16) { for x in stride(from:16,to:784,by:16) {
        let point=CGPoint(x:Double(x)+0.5,y:Double(y)+0.5)
        guard let index=polygons.indices.last(where:{inside(point,polygons[$0])}) else {continue}
        if polygons.contains(where:{p in p.indices.contains {distance(point,p[$0],p[($0+1)%p.count])<5}}) {continue}
        let polygon=polygons[index],xs=polygon.map(\.x),ys=polygon.map(\.y)
        let rect=CGRect(x:xs.min()!,y:ys.min()!,width:xs.max()!-xs.min()!,height:ys.max()!-ys.min()!),image=images[index],crop=crops[index]
        let scale=max(rect.width/Double(image.width),rect.height/Double(image.height))*crop["zoom"]!,w=Double(image.width)*scale,h=Double(image.height)*scale
        let left=min(rect.minX,max(rect.maxX-w,rect.midX-w*crop["centerX"]!)),top=min(rect.minY,max(rect.maxY-h,rect.midY-h*crop["centerY"]!))
        let sx=Int((point.x-left)/scale),sy=Int((point.y-top)/scale)
        guard sx>4 && sx<image.width-4 && sy>4 && sy<image.height-4 else {continue}
        if [image.width/3,image.width*2/3].contains(where:{abs(sx-$0)<4}) || abs(sy-image.height/2)<4 {continue}
        let base=image.pixel(sx,sy,flipped:flipped),actual=output.pixel(x,y,flipped:flipped),difference=delta(base,actual)
        if !boxes.contains(where:{$0.insetBy(dx:-8,dy:-8).contains(point)}) {maximum=max(maximum,difference);verified[index]+=1}
        else {for n in boxes.indices where boxes[n].insetBy(dx:8,dy:8).contains(point) && !boxes.indices.contains(where:{$0 != n && boxes[$0].contains(point)}) {if difference>20 {changed[n]+=1}}}
    } }
    try require(maximum<=2 && verified.allSatisfy {$0>5},"Independent source ordering/crop pixel oracle failed: \(maximum), samples \(verified)")
    try require(changed.allSatisfy {$0>0},"Each separately visible layer must change actual Photos pixels")
    print("TV_NATIVE_COMPOSITION_ORACLE count=\(count) sourceSamples=\(verified) maximumChannelDifference=\(maximum) layerChangedSamples=\(changed) keyboardExercised=\(expected["keyboardExercised"]!) readbackSHA256=\(digest)")
}
