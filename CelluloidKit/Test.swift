//
//  Test.swift
//  Celluloid
//
//  Created by Mango on 16/2/28.
//  Copyright © 2016年 Mango. All rights reserved.
//

import Foundation
import Async

public class hello{
    public static func hello(){
        Async.background{
            print("hello")
        }
    }
}