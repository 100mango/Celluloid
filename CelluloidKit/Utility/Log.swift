//
//  Log.swift
//  Celluloid
//
//  Created by Mango on 16/5/4.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation

public func
    Log(text: String,  fileName: String = #file, function: String =  #function, line: Int = #line) {
    debugPrint("[\((fileName as NSString).lastPathComponent), in \(function)() at line: \(line)]: \(text)")
}