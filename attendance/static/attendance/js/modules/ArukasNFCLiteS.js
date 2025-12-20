/*
*
*	JavaScript FeliCa Lite-S操作モジュール
*		ArukasNFCLiteS.js
*		import { ArukasNFCLiteS } from './modules/ArukasNFCLiteS.js';
*	メンテナンス履歴
*		2022/05/23 Ver.1.0.0 新規作成
*		2022/06/07 Ver.1.0.1 USBデバイス(カードリーダー)コネクト処理 改善のため修正 connectUSBDevice()
*
*******************************************************************/

class ArukasNFCLiteS {

	static Errors = {
		100 : 'RDRヘッダの連番が異なっている(Recive)' ,
		101 : 'Slotのステータス正常(Recive)' ,
		104 : 'ICCが存在しアクティブです(Recive)' ,
		105 : 'ICCが存在し非アクティブです(Recive)' ,
		106 : 'ICCが存在しません(Recive)' ,
		110 : 'メモリ書き換え回数が上限を超えています(Write)' ,
		120 : 'ポーリング不可カード未検出' ,
		130 : 'ポーリングによりカード検出されていません' ,
	// 500番以上をエラーとします
		501 : 'RDRヘッダの長さが10バイト以下(Recive)' ,
		502 : 'RDRヘッダのタイプが0x83以外です(Recive)' ,
		503 : 'RDRヘッダのスロットが0以外です(Recive)' ,
		504 : 'Slotのステータスがエラー(Recive)' ,
		505 : 'Slotの時間延長が要求された(Recive)' ,
		510 : 'レスポンスエラー (Status1 0x90 Status2 0x00 以外)' ,
		511 : 'レスポンスエラー(0xC0 0x03 以外)' ,
		512 : 'レスポンスエラー(0x00 0x90 0x00 以外)' ,
		513 : 'レスポンスレングスサイズ取得エラー(レスポンスヘッダのデータ長が128バイト以上の時のサイズ取得に失敗)' ,
		514 : 'レスポンスレングスエラー(レスポンスヘッダのデータ長より実データ長が小さい)' ,
		520 : 'USB Device TransferOutで転送要求失敗' ,
		521 : 'USB Device TransferOutで転送要求したバイト数が転送要素のバイト数より少ない' ,
		530 : 'USB Device クローズ失敗' ,
		540 : 'USB Device Receive リクエストバイト数が不正',
		541 : 'USB Device Receive タイムアウト',
		550 : 'USB Device TransferInで受信要求失敗',
		560 : 'ポーリングのレスポンスコードが不正(01h以外)',
		570 : '読み込みのレスポンスコードが不正(07h以外)',
		571 : '読み込み時に致命的なメモリエラー発生 ステータス2 0x70',
		572 : '読み込み時にエラー発生',
		580 : '書き込みのレスポンスコードが不正(09h以外)',
		581 : '書き込み時に致命的なメモリエラー発生 ステータス2 0x70',
		582 : '書き込み時にエラー発生',
		900 : 'カードリーダーがサポート外の機種です' ,
		990 : '',
	}

	constructor( argOpt ) {

		this.WARNING = argOpt?.warning ?? true ;
		this.DEBUG = argOpt?.debug ?? false ;
		
		this.curSeq = 0 ;
		this.mProcName = '' ;
		
		this.ERRORFREE = false ;
		
		this.USBDevice = null ;
		this.USBDeviceConfig = {} ;
		this.USBRecvBuffer = [] ;
		this.USBRecv = null ;

		this.DEVICEINFOLIST = {		// ペアリング対応機種リスト
			1729 : {
				vendorId : 1356 ,
				productId:1729,
				modelName:"RC-S380/S",
				deviceType:"External"
			}	,
			1731 : {
				vendorId : 1356 ,
				productId:1731,
				modelName:"RC-S380/P",
				deviceType:"External"
			}	,
			3528 : {
				vendorId : 1356 ,
				productId: 3528 ,
				modelName: "RC-S300/S" ,
				deviceType: "External"
			} ,
			3529 : {
				vendorId : 1356 ,
				productId: 3529 ,
				modelName: "RC-S300/P" ,
				deviceType: "External"
			}	,
		}

		this.FelicaConfig = {
			Polling : false ,
		} ;

		this.cL = () => {} ;
		if ( this.DEBUG === true ) {
			this.cL = console.log ;			// for Debug code
		}
		
		this.EcL = () => {} ;
		this.WcL = () => {} ;
		this.EcL = console.error ;		// エラーメッセージ表示
		if ( this.WARNING === true ) {
			this.WcL = console.log ;		// ワーニングメッセージ表示
		}
		
		this.DEVICEFILTERS = [] ;		// ペアリング時のフィルタ
		for( let pid in this.DEVICEINFOLIST ) {
			let vend = this.DEVICEINFOLIST[pid].vendorId ;
			this.DEVICEFILTERS.push( { vendorId : vend , productId : pid } ) ;
		}

		this.MAX_RECIEVESIZE = 513 ;
		this.TRANCEVE_TAG = 0x95 ;
		this.SLOTNUMBER = 0 ;
	}

	/*
	*	USBデバイス(カードリーダー)コネクト
	----------------------------------------------------------------------*/
	async connectUSBDevice() {
		this.cL( 'connectUSBDevice : begin' ) ;
		this.mProcName = 'Connect USBDevice' ;

		const ud = await navigator.usb.getDevices() ;						// ペアリング設定済みデバイスのUSBDeviceインスタンス取得
		let peared = 0 ;
		if ( ud.length > 0 ) {
			for( let dev of ud ) {
				const td = this.DEVICEFILTERS.find( (fildev) => dev.vendorId == fildev.vendorId && dev.productId == fildev.productId ) ;
				if ( td !== undefined ) {
					++peared ;
					this.USBDevice = dev ;
				}
			}
		}
		if ( peared != 1 ) {
			this.USBDevice = await navigator.usb.requestDevice( { filters: this.DEVICEFILTERS } ) ;	// USB機器をペアリングフローから選択しデバイスのUSBDeviceインスタンス取得
		}

		let proId = this.USBDevice.productId ;
		if (  proId in this.DEVICEINFOLIST === false ) {
			let e = { code: 900, message: 'プロダクトID:' + proId } ;
			this.putErrorMsg( e ) ;
		}

		this.USBDeviceConfig.ProductId = proId ;
		this.USBDeviceConfig.ModelName = this.DEVICEINFOLIST[ proId ].modelName ;
		this.USBDeviceConfig.DeviceType = this.DEVICEINFOLIST[ proId ].deviceType ;
		this.USBDeviceConfig.MamufacturerName = this.USBDevice.manufacturerName ;
		this.USBDeviceConfig.SerialNumber = this.USBDevice.serialNumber ;
		this.USBDeviceConfig.ProductName = this.USBDevice.productName ;
		
		this.USBDeviceConfig.Fillters = { ...this.DEVICEFILTERS } ;
		this.USBDeviceConfig.confValue = this.USBDevice.configuration.configurationValue ;
		this.USBDeviceConfig.intfaceNum = this.USBDevice.configuration.interfaces[ this.USBDeviceConfig.confValue ].interfaceNumber ;	// インターフェイス番号
		let ep = this.getEndPoint('in') ;
		this.USBDeviceConfig.endPointInNum = ep.endpointNumber ;			// 入力エンドポイント
		this.USBDeviceConfig.endPointInPacketSize = ep.packetSize ;			// 入力パケットサイズ
		ep = this.getEndPoint('out') ;
		this.USBDeviceConfig.endPointOutNum = ep.endpointNumber ;			// 出力エンドポイント
		this.USBDeviceConfig.endPointOutPacketSize = ep.packetSize ;		// 出力パケットサイズ

		this.cL( 'connectUSBDevice : end', this.USBDevice, this.USBDeviceConfig ) ;
		this.mProcName = '' ;
		return this.USBDevice ;
	}

	/*
	*	USBデバイス(カードリーダー) Endpoint の取得
	*		argVal : 'in' or 'out'
	----------------------------------------------------------------------*/
	getEndPoint( argVal ) {
		let retVal = false ;
		for( const val of this.USBDevice.configuration.interfaces[ this.USBDevice.configuration.configurationValue ].alternate.endpoints ) {
			if ( val.direction == argVal ) { retVal = val ; }
		}
		return retVal ;
	}
	
	/*
	*	USBデバイス(カードリーダー)オープン
	----------------------------------------------------------------------*/
	async openUSBDevice() {
		this.cL( 'openUSBDevice : begin' ) ;
		this.mProcName = 'Open USBDevice' ;

		const USBSETUPCOM = {
//			FirmwareVersion :         { Com : [ 0xFF, 0x56, 0x00, 0x00 ], Sleep : 0 } ,
			EndTransparentSession :   { Com : [ 0xFF, 0x50, 0x00, 0x00, 0x02, 0x82, 0x00, 0x00 ], Sleep : 0 } ,
			StartTransparentSession : { Com : [ 0xFF, 0x50, 0x00, 0x00, 0x02, 0x81, 0x00, 0x00 ], Sleep : 0 } ,
			TurnOffTheRF :            { Com : [ 0xFF, 0x50, 0x00, 0x00, 0x02, 0x83, 0x00, 0x00 ], Sleep : 30 } ,
			TurnOnTheRF :             { Com : [ 0xFF, 0x50, 0x00, 0x00, 0x02, 0x84, 0x00, 0x00 ], Sleep : 30 } ,
			SwitchProtocolTypeF :     { Com : [ 0xFF, 0x50, 0x00, 0x02, 0x04, 0x8F, 0x02, 0x03, 0x00, 0x00 ], Sleep : 0 } ,
//			DeviceType :              { Com : [ 0xFF, 0x5F, 0x08, 0x00 ], Sleep : 0 } ,
//			SerialNumber :            { Com : [ 0xFF, 0x5F, 0x03, 0x00 ], Sleep : 0 } ,
		}

		await this.USBDevice.open();
		await this.USBDevice.selectConfiguration( this.USBDeviceConfig.confValue );
		await this.USBDevice.claimInterface( this.USBDeviceConfig.intfaceNum );

		this.FelicaConfig.Polling = false ;
		this.USBDeviceConfig.Open = {} ;

		await this.contrlCommUSBDevice( USBSETUPCOM, this.USBDeviceConfig.Open ) ;

/*
		// ファームウェアバージョン
		this.USBDeviceConfig.FirmwereVersion = this.USBDeviceConfig.Open.FirmwareVersion[2] + '.' + 
		                                      this.USBDeviceConfig.Open.FirmwareVersion[1] + '.' + 
		                                      this.USBDeviceConfig.Open.FirmwareVersion[0] + '.' + 
		                                      this.USBDeviceConfig.Open.FirmwareVersion[3] + '.' + 
		                                      this.USBDeviceConfig.Open.FirmwareVersion[4] ;	// ファームウェアバージョンの順番がよくわからないが USBDeviceのdeviceVersionMajor: 1 deviceVersionMinor: 0 deviceVersionSubminor: 0 となっていたのでこんな順序にしています。
		// デバイスタイプ 1:Internal 2:External
		let devT = this.USBDeviceConfig.Open.DeviceType[4] ;
		let dt = '' ;
		devT == 1 ? dt = 'Internal' : devT == 2 ? dt = 'External' : dt = this.USBDeviceConfig.DeviceType ;
		this.USBDeviceConfig.DeviceType = dt ;
		// シリアル番号
		let serN = '' ;
		this.USBDeviceConfig.Open.SerialNumber.forEach( (e) => { serN += String.fromCharCode(e) } )
		this.USBDeviceConfig.SerialNumber = serN ;
*/
		this.cL( 'openUSBDevice : end', this.USBDeviceConfig ) ;
		this.mProcName = '' ;
	}

	/*
	*	USBデバイス(カードリーダー)制御コマンド
	----------------------------------------------------------------------*/
	async contrlCommUSBDevice( argCom, argRes ) {
		for( let key in argCom ) {
			this.cL( '*--*' + key + ' : Start' ) ;
			const setupcom = argCom[ key ] ;
			const res = await this.escapeTranceferTarget( setupcom.Com, 400 ) ;
			argRes[ key ] =  this.array_slice( res, 0, res.length - 2 ) ;		// Statusを削除
			this.cL( '*--*' + key + ' : End', this.array_tohexs( argRes[ key ] ) ) ;
			if ( setupcom.Sleep > 0 ) { await this.sleep( setupcom.Sleep ) ; }
		}
	}
	
	/*
	*	USBデバイス(カードリーダー)クローズ
	----------------------------------------------------------------------*/
	async closeUSBDevice() {
		let retVal = true ;
		this.cL( 'closeUSBDevice : begin' ) ;
		this.mProcName = 'Close USBDevice' ;

		const USBSETUPCOM = {
			TurnOffTheRF :            { Com : [ 0xFF, 0x50, 0x00, 0x00, 0x02, 0x83, 0x00, 0x00 ], Sleep : 30 } ,
			EndTransparentSession :   { Com : [ 0xFF, 0x50, 0x00, 0x00, 0x02, 0x82, 0x00, 0x00 ], Sleep : 0 } ,
		}

		if ( this.USBDevice != null ) {
			try {
				this.USBDeviceConfig.Close = {} ;
				await this.contrlCommUSBDevice( USBSETUPCOM, this.USBDeviceConfig.Close ) ;
				
				await this.USBDevice.close() ;
			}
			catch( r ) {
				e( r.message ) ;
				retVal = { code: 530, message: r.message } ;
				this.putErrorMsg( retVal ) ;
			}
			this.USBDevice = null ;
			this.USBDeviceConfig = {} ;
			this.USBRecvBuffer = [] ;
			this.USBRecv = null ;
			this.FelicaConfig.Polling = false ;
		}
		this.sleep(30);
		this.cL( 'closeUSBDevice : end' ) ;
		this.mProcName = '' ;
		return retVal ;
	}
	
	/*
	*	USBデバイス(カードリーダー) Transmit
	----------------------------------------------------------------------*/
	async transmitUSBDevice( argVal ) {
		let res = {} ,
			retVal = { Error : this.ERRORFREE } ;
		
		this.cL( 'transmitUSBDevice : begin' ) ;
		let epNum = this.USBDeviceConfig.endPointOutNum ;					// 出力エンドポイント
		let pktSz = this.USBDeviceConfig.endPointOutPacketSize ;			// 出力パケットサイズ
		this.cL( '*-* Send length : %d Max packetsize : %d', argVal.length, pktSz ) ;
		this.cL( '*-* Send : ', this.array_tohexs( argVal, ' ' ) ) ;
		res = await this.USBDevice.transferOut( epNum, Uint8Array.from( argVal ))				// device.transferOut
			.then( ( r ) => {
				if ( r.status != 'ok' ) {
					retVal.Error = { code: 520, message: r.status } ;
				}
				if ( r.bytesWritten < argVal.length ) {
					retVal.Error = { code: 521, message: r.bytesWritten + 'バイト' } ;
				}
				return r ;
			}) ;
		this.cL( 'transmitUSBDevice : end', res, retVal ) ;
		return retVal ;
	}

	/*
	*	USBデバイス(カードリーダー) 受信バッファの取得
	----------------------------------------------------------------------*/
	getUSBDeviceBuffer( argLength ){
		let retVal = [] ;
		
		this.cL( 'getUSBDeviceBuffer : begin %d', argLength, this.array_tohexs( this.USBRecvBuffer ) ) ;
		
		if ( this.USBRecvBuffer.length >= argLength ) {
			retVal = this.array_slice( this.USBRecvBuffer, 0, argLength ) ;
			this.USBRecvBuffer = this.array_slice( this.USBRecvBuffer, argLength, this.USBRecvBuffer.length - argLength ) ;
		}
		
		this.cL( 'getUSBDeviceBuffer : end', this.array_tohexs( retVal ) ) ;
		return retVal ;
	}
	
	/*
	*	USBデバイス(カードリーダー) Receive
	----------------------------------------------------------------------*/
	async receiveUSBDevice( argLength, argTimeout ) {
		let retVal = { Error : this.ERRORFREE } ,
			stTime = new Date ,
			nowTime ,
			ticktack ,
			aborts = false ,
			promises = [] ;
		
		this.cL( 'receiveUSBDevice : begin Length %d Timeout %d', argLength, argTimeout ) ;
		
		if ( argLength <= 0 ) {
			retVal.Error = { code: 540, message: argLength + 'バイト' } ;
			this.putErrorMsg( retVal ) ;
		}
		
		if ( this.USBRecvBuffer.length >= argLength ) {										// 受信バッファにデータが残っている
			let d = this.getUSBDeviceBuffer( argLength ) ;
			retVal.data = d ;
			this.cL( '** receiveUSBDevice : from receive buffer ', retVal ) ;
			Promise.resolve( retVal ) ;
			return retVal ;
		}

		promises[0] = this.transferinUSBDevice()											// 受信処理
			.then ( () => {
				if ( aborts === false ) {
					if ( this.USBRecvBuffer.length < argLength ) {
						nowTime = new Date ;
						let t = nowTime.getTime() - stTime.getTime() ;						// 経過時間算出
						if ( t > argTimeout ) {
							retVal.Error = { code: 541, message: argTimeout + '(ms)' } ;	// タイムアウト
							retVal.data = [] ;
							Promise.reject( retVal ) ;
							return retVal ;
						} else {
							this.receiveUSBDevice( argLength, argTimeout - t ) ;			// タイムアウトまで再帰する。
						}
					} else {
						let d = this.getUSBDeviceBuffer( argLength ) ;
						retVal.data = d ;													// 受信成功
						this.cL( '** transferin success', retVal ) ;
						Promise.resolve( retVal ) ;
						return retVal ;
					}
				}
			})

		promises[1] = new Promise( () => { ticktack = setTimeout( () => {}, argTimeout ) })	// タイムアウト用タイマー
			.then( () => {
				aborts = true ;
				retVal.Error = { code: 541, message: argTimeout + '(ms)' } ;
				retVal.data = [] ;
				Promise.reject( retVal ) ;
				return retVal ;
			});

		retVal = await Promise.race( promises ) ;											// transferinとタイマーの待ち合わせ
		clearTimeout( ticktack ) ;
		
		this.cL( 'receiveUSBDevice : end', retVal ) ;
		return retVal ;
	}
	
	/*
	*	USBデバイス(カードリーダー) Transeferin
	----------------------------------------------------------------------*/
	async transferinUSBDevice() {
		let retVal = { Error : this.ERRORFREE } ;
		this.cL( 'transferinUSBDevice : begin' ) ;
		this.USBRecv = await this.USBDevice.transferIn( this.USBDeviceConfig.endPointInNum, this.MAX_RECIEVESIZE )					// device.transferIn !!!
			.then( r => {
				this.cL( "transferIn status : " + r.status ) ;
				this.cL( "  data.byteLength : " + r.data.byteLength) ;
				if ( r.status != 'ok' || r.data.byteLength == 0 ) {
					retVal.Error = { code: 550, message: r.status + ' ' + r.data.byteLength + 'バイト' } ;
					Promise.reject( retVal ) ;
					return retVal ;
				}
				let d = this.dataview_to_array( r.data ) ;
				this.cL("  transferIn data : " + this.array_tohexs( d ) ) ;
				this.array_copy( this.USBRecvBuffer, this.USBRecvBuffer.length, d, 0, d.length ) ;
				retVal.data = this.USBRecvBuffer ;
				this.USBRecv = null ;
				Promise.resolve( retVal ) ;
				return retVal ;
			}) ;
		this.cL( 'transferinUSBDevice : end' ) ;
	}
	
	/*
	*	USBデバイス(カードリーダー) 受信バッファのクリア
	----------------------------------------------------------------------*/
	async clearUSBDevice(){
		this.cL( 'clearUSBDevice : begin' ) ;
		this.USBRecvBuffer = [],
		this.cL( 'clearUSBDevice : end' ) ;
	}

	/*
	*	FeliCa カードのポーリング
	----------------------------------------------------------------------*/
	async pollingLiteS() {
		this.cL( '** pollingLiteS : begin' ) ;
		this.mProcName = 'Polling FeliCa Lite-S' ;
		
		const USBSETUPCOM = {
			SwitchProtocolTypeF :     { Com : [ 0xFF, 0x50, 0x00, 0x02, 0x04, 0x8F, 0x02, 0x03, 0x01, 0x00 ], Sleep : 0 } ,
			TargetCardBaudRate :      { Com : [ 0xFF, 0xCA, 0xF2, 0x00 ], Sleep : 0 } ,
		}

		/* Polling コマンド
		+	Length (1) 
		+	コマンドコード (1) 0x00
		+	システムコード (2) 0xff 0xff	<<ワイルドカード指定>>
		+	リクエストコード(1) 0x01		<<システムコード要求>>
		+	タイムスロット (1) 0x00
		+----------------------------------------------------------------------------------------------------*/
		const FelicaPollingCom = [ 0x00, 0x00, 0xff, 0xff, 0x01, 0x00 ] ;
		let pollingC = new Uint8Array( FelicaPollingCom ) ;
		pollingC[0] = pollingC.length ;															// Length のセット

		this.cL( 'pollingLiteS : Genarate Command :', this.array_tohexs( pollingC, ' ' ) ) ;

		let response = await this.manipulateCardErrorThru( pollingC, 100 )
			.then( ( ret ) => {
				this.cL(ret);
				this.FelicaConfig.Polling = false ;
				if ( ret.CodeStatus2[0] === 2 && ret.CodeStatus2[1] === 100 && ret.CodeStatus2[2] === 1 ) {	// カード未発見
					return { Error : { code: 120 , message: '' } } ;
				}
				let ResEr = this.checkResponseData( ret ) ;										// レスポンスデータをチェック
				this.putErrorMsg( ResEr ) ;
				
				let resObj = this.pollingResponse( ret.Data, pollingC ) ;
				this.cL( 'pollingLiteS : result :', resObj ) ;
				let eR = this.checkPollingResponseData( resObj ) ;
				this.putErrorMsg( eR ) ;
				
				this.FelicaConfig.Polling = true ;
				return resObj ;
			}).catch( (error) => {
				throw(error);
			});

		this.USBDeviceConfig.Polling = {} ;
		await this.contrlCommUSBDevice( USBSETUPCOM, this.USBDeviceConfig.Polling ) ;

		this.cL( '** pollingLiteS : end', response ) ;
		this.mProcName = '' ;
		
		return response ;
	}
		
	/*
	*	FeliCa カードのポーリング結果を加工
	----------------------------------------------------------------------*/
	pollingResponse( argRes, argCom ) {
		let retVal = {
			Error : this.ERRORFREE ,
			Id : + this.array_slice( argRes, 0, 1 ) ,
			ResponseCode : + this.array_slice( argRes, 1, 1 ) ,					// レスポンスコード
			IDm : this.array_slice( argRes, 2, 8 ) ,							// IDm (Array)
			PMm : this.array_slice( argRes, 10, 8 ) ,							// PMm (Array)
			SystemCode : this.array_slice( argRes, 18, 2) ,						// システムコード
			Status1 : 0 ,														// ステータスフラグ2
			Status2 : 0 ,														// ステータスフラグ2
			Command: argCom ,													// コマンド (Unit8Array)
			CommandString: this.array_tohexs( argCom ) ,						// コマンド (文字列16進表記)
			Response: argRes ,													// レスポンス (Unit8Array)
			ResponseString: this.array_tohexs( argRes ) ,						// レスポンス (文字列16進表記)
		} ;
		retVal.IDmString = this.array_tohexs( retVal.IDm ) ;	// IDm (文字列16進表記)
		retVal.PMmString = this.array_tohexs( retVal.PMm ) ;	// IDm (文字列16進表記)
		retVal.SystemCodeString = this.array_tohexs( retVal.SystemCode ) ;	// IDm (文字列16進表記)
		
		// USBDevice Configuration Setting
		this.FelicaConfig.IDm = retVal.IDm ;
		this.FelicaConfig.PMm = retVal.PMm ;
		this.FelicaConfig.SystemCode = retVal.SystemCode ;
		return retVal ;
	}
	
	/*
	*	FeliCa カードのポーリング結果をチェック
	----------------------------------------------------------------------*/
	checkPollingResponseData( argResObj ) {
		let msg = '' ;
		if ( argResObj.ResponseCode != 0x01 ) {
			msg = this.bytes2hexs( [ resObj.ResponseCode ] ) ;
			return  { code: 560, message: msg } ;
		}
		return this.ERRORFREE ;
	}

	/*
	*	FeliCa Lite-S カードの読み込み
	----------------------------------------------------------------------*/
	async readLiteS( argOpt ) {
		this.cL( '** readLiteS : begin' ) ;
		this.mProcName = 'Read FeliCa Lite-S' ;
		
		/* Read Without Encryption コマンド ( サービス数とサービスコードは固定 )
		+	Length (1) 
		+	コマンドコード (1) 0x06
		+	IDm (8)
		+	サービス数 (1) 1
		+	サービスコード (2) 0x00 0x90 <<リトルエンディアン>>
		+----------------------------------------------------------------------------------------------------*/
		const FelicaReadCom = [ 0x00, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 1, 0x09, 0x00 ] ;

		if ( this.FelicaConfig.Polling === false ) {
			return { Error : { code: 130 , message: '(Read)' } } ;
		}

		// コマンドに ReadOption を反映させる (読み込みブロックアドレスを追加する)
		let readComm = [ ...FelicaReadCom ] ;
		readComm.push( argOpt.Block.length ) ;		// ブロック数
		for( let blk of argOpt.Block ) {			// ブロックリスト
			readComm.push( 0x80 ) ;
			readComm.push( blk ) ;
		}

		let readC = new Uint8Array( readComm ) ;
		this.array_copy( readC, 2, this.FelicaConfig.IDm, 0, this.FelicaConfig.IDm.length ) ;	// IDm のセット
		readC[0] = readC.length ;																// Length のセット

		this.cL( 'readLiteS : Genarate Command :', this.array_tohexs( readC, ' ' ) ) ;

		let response = await this.manipulateCard( readC, 100 )
			.then( ( ret ) => {
				let resObj = this.readResponse( ret.Data, readC ) ;
				this.cL( 'readLiteS : result :', resObj ) ;
				let eR = this.checkReadResponseData( resObj ) ;
				this.putErrorMsg( eR ) ;
				let dataStr = resObj.DataString ;
				return resObj ;
			}, (error) => {
				throw(error);
			});

		this.cL( '** readLiteS : end' ) ;
		this.mProcName = '' ;
		
		return response ;
	}
	
	/*
	*	FeliCa Lite-S カードの読み込み結果を加工
	----------------------------------------------------------------------*/
	readResponse( argRes, argCom ) {
		let retVal = {
			Error : this.ERRORFREE ,
			Id : + this.array_slice( argRes, 0, 1 ) ,
			ResponseCode : + this.array_slice( argRes, 1, 1 ) ,					// レスポンスコード
			IDm : this.array_slice( argRes, 2, 8 ) ,							// IDm (Array)
			Status1 : + this.array_slice( argRes, 10, 1) ,						// ステータスフラグ1
			Status2 : + this.array_slice( argRes, 11, 1) ,						// ステータスフラグ2
			BlockCount : + this.array_slice( argRes, 12, 1) ,					// ブロック数
			Data : this.array_slice( argRes, 13, argRes.length - 13 ) ,			// ブロックデータ
			Command: argCom ,													// コマンド (Unit8Array)
			CommandString: this.array_tohexs( argCom ) ,						// コマンド (文字列16進表記)
			Response: argRes ,													// レスポンス (Unit8Array)
			ResponseString: this.array_tohexs( argRes ) ,						// レスポンス (文字列16進表記)
		} ;
		retVal.IDmString = this.array_tohexs( retVal.IDm ) ;					// IDm (文字列16進表記)
		retVal.DataString = '' ;
		retVal.Datas = [] ;
		retVal.DatasString = [] ;
		for( let i = 0, offset = 13, blockLength = 16 ; i < retVal.BlockCount ; ++i, offset += blockLength ) {
			retVal.Datas[i] = this.array_slice( argRes, offset, blockLength ) ;	// ブロックデータ分割
			retVal.DatasString[i] = this.binToString( retVal.Datas[i] ) ;		// ブロックデータ文字列変換
			retVal.DatasString[i] = retVal.DatasString[i].trim(' ') ;			// ブロックデータの空白文字の除去
		}
		retVal.DataString = retVal.DatasString.toString() ;						// ブロックデータ
		return retVal ;
	}
	
	/*
	*	FeliCa Lite-S カードの読み込み結果をチェック
	----------------------------------------------------------------------*/
	checkReadResponseData( argResObj ) {
		let msg = '' ;
		if ( argResObj.ResponseCode != 0x07 ) {
			msg = this.bytes2hexs( [ argResObj.ResponseCode ] ) ;
			return  { code: 570, message: msg } ;
		}
		if ( argResObj.Status2 == 0x70 ) {
			msg = this.bytes2hexs( [ argResObj.Status1, argResObj.Status2  ] ) ;
			return  { code: 571, message: msg } ;
		}
		if ( argResObj.Status1 != 0x00 || argResObj.Status2 != 0x00 ) {
			msg = this.bytes2hexs( [ argResObj.Status1, argResObj.Status2  ] ) ;
			return  { code: 572, message: msg } ;
		}
		return this.ERRORFREE ;
	}

	/*
	*	FeliCa Lite-S カードの書き込み
	----------------------------------------------------------------------*/
	async writeLiteS( argOpt ) {
		let response = [] ,
			resCount = 0 ;
		
		this.cL( '** writeLiteS : begin' ) ;
		this.mProcName = 'Write FeliCa Lite-S' ;
		/* Read Without Encryption コマンド ( サービス数とサービスコードは固定 )
		+	Length (1) 
		+	コマンドコード (1) 0x08
		+	IDm (8)
		+	サービス数 (1) 1
		+	サービスコード (2) 0x00 0x90 <<リトルエンディアン>>
		+	ブロック数 (1) 1
		+----------------------------------------------------------------------------------------------------*/
		const FelicaWriteCom = [ 0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 1, 0x09,0x00, 1 ] ;

		if ( this.FelicaConfig.Polling === false ) {
			this.cL( 'writeLiteS : Polling Error' ) ;
			return { Error : { code: 130 , message: '(Write)' } } ;
		}

		for( let opt of argOpt.Datas ) {
			// コマンドに WriteOption を反映させる (書き込みブロックリストとブロックエレメントを追加する)
			let writeComm = [ ...FelicaWriteCom ] ;
			// ブロックリスト
			writeComm.push( 0x80 ) ;
			writeComm.push( opt.Block ) ;
			// ブロックエレメント
			opt.Data = opt.Data.padEnd( 16 , ' ' ) ;		// エレメントの後ろは空白で埋める
			for( let str of opt.Data ) {
				writeComm.push( str.charCodeAt(0) ) ;
			}
			let writeC = new Uint8Array( writeComm ) ;
			this.array_copy( writeC, 2, this.FelicaConfig.IDm, 0, this.FelicaConfig.IDm.length ) ;	// IDm のセット
			writeC[0] = writeC.length ;																// Length のセット

			this.cL( 'writeLiteS : Genarate Command :', this.array_tohexs( writeC, ' ' ) ) ;

			response[ resCount ] = await this.manipulateCard( writeC, 100 )
				.then( ( ret ) => {
					let resObj = this.writeResponse( ret.Data, writeC ) ;
					this.cL( 'writeLiteS : result :', resObj ) ;
					let eR = this.checkWriteResponseData( resObj ) ;
					this.putErrorMsg( eR ) ;
					let dataStr = resObj.DataString ;
					return resObj ;
				}, (error) => {
					throw(error);
				});
			
			++resCount ;
		}

		this.cL( '** writeLiteS : end', response ) ;
		this.mProcName = '' ;
		return response ;
	}
	
	/*
	*	FeliCa Lite-S カードの書き込み結果を加工
	----------------------------------------------------------------------*/
	writeResponse( argRes, argCom ) {
		let retVal = {
			Error : this.ERRORFREE ,
			Id : + this.array_slice( argRes, 0, 1 ) ,
			ResponseCode : + this.array_slice( argRes, 1, 1 ) ,					// レスポンスコード
			IDm : this.array_slice( argRes, 2, 8 ) ,							// IDm (Array)
			Status1 : + this.array_slice( argRes, 10, 1) ,						// ステータスフラグ1
			Status2 : + this.array_slice( argRes, 11, 1) ,						// ステータスフラグ2
			Command: argCom ,													// コマンド (Unit8Array)
			CommandString: this.array_tohexs( argCom ) ,						// コマンド (文字列16進表記)
			Response: argRes ,													// レスポンス (Unit8Array)
			ResponseString: this.array_tohexs( argRes ) ,						// レスポンス (文字列16進表記)
		} ;
		retVal.IDmString = this.array_tohexs( retVal.IDm ) ;					// IDm (文字列16進表記)
		return retVal ;
	}
	
	/*
	*	FeliCa Lite-S カードの書き込み結果をチェック
	----------------------------------------------------------------------*/
	checkWriteResponseData( argResObj ) {
		let msg = '' ;
		if ( argResObj.ResponseCode != 0x09 ) {
			msg = this.bytes2hexs( [ argResObj.ResponseCode ] ) ;
			return  { code: 580, message: msg } ;
		}
		if ( argResObj.Status2 == 0x70 ) {
			msg = this.bytes2hexs( [ argResObj.Status1, argResObj.Status2  ] ) ;
			return  { code: 581, message: msg } ;
		}
		if ( argResObj.Status2 == 0x71 ) {
			msg = this.bytes2hexs( [ argResObj.Status1, argResObj.Status2  ] ) ;
			return  { code: 110, message: msg } ;
		}
		if ( argResObj.Status1 != 0x00 || argResObj.Status2 != 0x00 ) {
			msg = this.bytes2hexs( [ argResObj.Status1, argResObj.Status2  ] ) ;
			return  { code: 582, message: msg } ;
		}
		return this.ERRORFREE ;
	}
	
	/*
	*	カードの操作 エラーチェックあり
	*		実処理は manipulateCardErrorThru にて行います。
	*		ホストコントローラが指定したデータをそのままRFコマンドパケットとしてTargetに送信
	*		argCom		コマンド (t)
	*		argTimeout		タイムアウト 100 (i)
	----------------------------------------------------------------------*/
	async manipulateCard( argCom, argTimeout ) {
		this.cL( 'manipulateCard : begin', this.array_tohexs( argCom ) ) ;

		let Res = await this.manipulateCardErrorThru( argCom, argTimeout ) ;
		let ResEr = this.checkResponseData( Res ) ;											// レスポンスデータをチェック
		this.cL( "manipulateCard : ResponseErr", ResEr ) ;
		this.putErrorMsg( ResEr ) ;
		
		this.cL( 'manipulateCard : end') ;
		return  Res ;

	}
	
	/*
	*	カードの操作 エラーチェックなし
	*		ホストコントローラが指定したデータをそのままRFコマンドパケットとしてTargetに送信
	*		argCom		コマンド (t)
	*		argTimeout		タイムアウト 100 (i)
	----------------------------------------------------------------------*/
	async manipulateCardErrorThru( argCom, argTimeout ) {
		this.cL( 'manipulateCardErrorThru : begin', this.array_tohexs( argCom ) ) ;

		argTimeout = argTimeout || 100 ;

		let Ccom = [] ;
		let zz = argTimeout ;
		
		argTimeout *= 1e3 ;		// マイクロ秒へ変換
		Ccom.push( 0x5f, 0x46, 0x04, 255 & argTimeout, argTimeout >> 8 & 255, argTimeout >> 16 & 255, argTimeout >> 24 & 255 ) ;		// 5F 46 04 i*1000 <<リトルエンディアン>> 4バイト
		Ccom.push( this.TRANCEVE_TAG, 0x82, argCom.length >> 8 & 255, 255 & argCom.length ) ;
		Ccom.push( ...argCom ) ;

		this.cL("manipulateCardErrorThru : Ccom", this.array_tohexs( Ccom )) ;
		
		let Rcom = [] ;
		Rcom.push( 0xff, 0x50, 0x00, 0x01, 0x00, Ccom.length >> 8 & 255, 255 & Ccom.length ) ,			// FF 50 00 01 00 length
		Rcom.push( ...Ccom ) ,
		Rcom.push( 0x00, 0x00, 0x00 ) ;

		this.cL("manipulateCardErrorThru : Rcom", this.array_tohexs( Rcom )) ;
		
		let resAll = await this.escapeTranceferTarget( Rcom, 400 ) ;								// ターゲットへコマンドをトランスファする。
		this.cL("manipulateCardErrorThru : recv", this.array_tohexs( resAll )) ;
		
		let Res = this.disassembleResponseData( resAll ) ;											// レスポンスデータを分解
		this.cL( "manipulateCardErrorThru : ResponseData", Res ) ;

		this.cL( 'manipulateCardErrorThru : end') ;
		
		return  Res ;
	}

	/*
	*	レスポンスデータの分解
	----------------------------------------------------------------------*/
	disassembleResponseData( argRes ) {
		let retVal = {
			Code : 0 ,							// レスポンスヘッダコード 通常 0xC0
			CodeStatus1 : 0 ,					// レスポンスヘッダのステータス 通常 0x03
			CodeStatus2 : [ 0, 0, 0 ] ,			// レスポンスヘッダのステータス 通常 0x00 0x90 0x00
			Status92 : 0 ,						// レスポンスヘッダの 0x92 に続くステータス
			Status96 : 0 ,						// レスポンスヘッダの 0x96 に続くステータス
			Length : 0 ,						// レスポンスヘッダのレスポンスデータ長 0x97 に続く 1～4バイト
			Status1 : 0,						// レスポンスデータの最後に付くステータス 通常 0x90
			Status2 : 0,						// レスポンスデータの最後に付くステータス 通常 0x00
			Data : [] ,							// レスポンスデータ
		} ;
		let v ;
		let c = argRes.slice( argRes.length - 2 ) ;
		retVal.AllData = argRes ;				// レスポンスヘッダを含むレスポンスデータ
		retVal.Status1 = c[0] ;
		retVal.Status2 = c[1] ;
		v = argRes.indexOf(0xc0) ;
		if ( v >= 0 ) {
			retVal.Code = argRes[v] ;
			retVal.CodeStatus1 = argRes[ v + 1 ] ;
			retVal.CodeStatus2 = this.array_slice( argRes, v + 2, 3 ) ;
		}
		v = argRes.indexOf(0x92) ;
		if ( v >= 0 ) { retVal.Status92 = argRes[ v + 1 ] ; }
		v = argRes.indexOf(0x96) ;
		if ( v >= 0 ) { retVal.Status96 = argRes[ v + 1 ] ; }
		// レスポンスデータ長の取得
		v = argRes.indexOf(0x97) ;
		if ( v >= 0 ) {
			let w = v + 1 ;
			retVal.Length = argRes[ w ] ;
			if ( retVal.Length >= 128 ) {
				switch( retVal.Length ) {
					case 129 :
						retVal.Length = argRes[ w + 1 ] ;
						w += 1 ;
						break ;
					case 130 :
						retVal.Length = ( argRes[ w + 1 ] << 8 ) + argRes[ w + 2 ] ;
						w += 2 ;
						break ;
					case 131 :
						retVal.Length = ( argRes[ w + 1 ] << 16 ) + ( argRes[ w + 2 ] << 8 ) + argRes[ w + 3 ] ;
						w += 3 ;
						break ;
					case 132 :
						retVal.Length = ( argRes[ w + 1 ] << 24 ) + ( argRes[ w + 2 ] << 16 ) + ( argRes[ w + 3 ] << 8 ) + argRes[ w + 4 ] ;
						w += 4 ;
						break ;
					default :
						retVal.Length = -1 ;
				}
			}
			if ( retVal.Length > 0 ) {
				retVal.Data = this.array_slice( argRes, w + 1, retVal.Length ) ;
			}
		}
		return retVal ;
	}

	/*
	*	レスポンスをチェック
	----------------------------------------------------------------------*/
	checkResponseData( argResObj ) {
		let msg = '' ;
		// レスポンスヘッダのチェック
		if ( argResObj.Status1 != 0x90 || argResObj.Status2 != 0 ) {
			msg = this.bytes2hexs( [ argResObj.Status1, argResObj.Status2 ] ) ;
			return  { code: 510, message: msg } ;
		}
		if ( argResObj.CodeStatus1 != 0x03 ) {
			msg = this.bytes2hexs( [ argResObj.CodeStatus1 ] ) ;
			return { code: 511, message: msg } ;
		}
		if ( argResObj.CodeStatus2[0] != 0x00 || argResObj.CodeStatus2[1] != 0x90 || argResObj.CodeStatus2[2] != 0x00 ) {
			msg = this.bytes2hexs( [ argResObj.CodeStatus2 ] ) ;
			return { code: 512, message: msg } ;
		}
		// レスポンスデータ長のチェック
		if ( argResObj.Length < 0 ) { 
			return { code: 513, message: msg } ;
		}
		if ( argResObj.Length > argResObj.Data.length ) {
			msg = '取得データ長[' + argResObj.Length + ']:実データ長[' + argResObj.Data.length + ']'
			return { code: 514, message: msg } ;
		}
		return this.ERRORFREE ;
	}
	
	/*
	*	カードの操作 Communicate Thru EX
	*		ホストコントローラが指定したデータをそのままRFコマンドパケットとしてTargetに送信
	*		argCom		コマンド (t)
	*		argTimeout		タイムアウト 100 (i)
	----------------------------------------------------------------------*/
	async escapeTranceferTarget( argCom, argRecvTimeout ) {
		this.cL( 'escapeTranceferTarget : begin', argRecvTimeout ) ;

		let retVal = [] ,
			res ,
			seqNum = this.getSeqNum() ;

		let Tcom = this.assembleRDRHeader( argCom, seqNum ) ;										// RDRヘッダーを付加

		this.cL( "escapeTranceferTarget : Tcom", this.array_tohexs( Tcom ) ) ;

		res = await this.transmitUSBDevice( Tcom ) ;												// transmit
		this.putErrorMsg( res.Error ) ;

		await this.clearUSBDevice() ;
		res = await this.receiveUSBDevice( 10, argRecvTimeout ) ;									// ヘッダー分 10バイト取得
		this.putErrorMsg( res.Error ) ;
		let RDRHeader = res.data ;
		
		let RDRRes = this.disassembleRDRHeader( RDRHeader ) ;										// RDRヘッダーを分解
		this.cL( "escapeTranceferTarget : RDRHeader", RDRRes ) ;
		let RDREr = this.checkRDRHeader( RDRRes, seqNum ) ;											// RDRヘッダーをチェック
		this.putErrorMsg( RDREr ) ;
		
		this.cL( "escapeTranceferTarget : RDRData", RDRRes.Length ) ;
		res = await this.receiveUSBDevice( RDRRes.Length, argRecvTimeout ) ;
		this.cL( "escapeTranceferTarget : RDRData res", res ) ;
		this.putErrorMsg( res.Error ) ;
		retVal = res.data ;
		this.cL( 'escapeTranceferTarget end', this.array_tohexs( retVal ) ) ;
		return retVal ;
	}

	/*
	*	連番を作成
	----------------------------------------------------------------------*/
	getSeqNum() {
		this.curSeq++ ;
		this.curSeq > 255 && ( this.curSeq = 0 ) ;
		return this.curSeq ;
	}
	
	/*
	*	RDRヘッダーを付加
	----------------------------------------------------------------------*/
	assembleRDRHeader( argCom, argSeqnum ) {

		const comLen = argCom.length ;

		let RDRcom = new Uint8Array( 10 + comLen ) ;

		RDRcom[0] = 0x6b ;						// ヘッダー作成
		RDRcom[1] = 255 & comLen ;				// length をリトルエンディアン
		RDRcom[2] = comLen >> 8 & 255 ;
		RDRcom[3] = comLen >> 16 & 255 ;
		RDRcom[4] = comLen >> 24 & 255 ;
		RDRcom[5] = this.SLOTNUMBER ;			// タイムスロット番号
		RDRcom[6] = argSeqnum ;					// 連番

		0 != comLen && RDRcom.set( argCom, 10 ) ;	// コマンド追加

		return RDRcom ;
	}

	/*
	*	RDRヘッダーを分解
	----------------------------------------------------------------------*/
	disassembleRDRHeader( argRDRHeader ) {

		let retVal = {
			Data : argRDRHeader ,
			HeaderLength : argRDRHeader.length ,
			Type : argRDRHeader[0] ,								// 0x83
			Length : argRDRHeader[4] << 24 | argRDRHeader[3] << 16 | argRDRHeader[2] << 8 | argRDRHeader[1] ,
			Slot : argRDRHeader[5] ,
			SeqNum : argRDRHeader[6] ,
			ICCStatus : 3 & argRDRHeader[7] ,						// 0:Normal
			ComStatus : argRDRHeader[7] >> 6 & 3 ,					// 2:Normal
			HeaderError : argRDRHeader[8] ,								// 0:Normal
		}
		return retVal ;
	}

	/*
	*	RDRヘッダーをチェック
	----------------------------------------------------------------------*/
	checkRDRHeader( argRDRRes , argSeq ) {
		let msg ;
		if ( argRDRRes.HeaderLength < 10 ) { return { code: 501, message: argRDRRes.HeaderLength.toString() } }
		if ( argRDRRes.Type != 0x83 ) { return { code: 502, message: '' } }
		if ( argRDRRes.Slot != this.SLOTNUMBER ) { return { code: 504, message: argRDRRes.Slot.toString() } }
		if ( argRDRRes.SeqNum != argSeq ) { return { code: 100, message: '[' + argRDRRes.SeqNum.toString() + ']-[' + argSeq.toString() + ']' } }
		if ( argRDRRes.ComStatus == 0 ) { return { code: 101, message: '' } }
		if ( argRDRRes.ComStatus == 1 ) { return { code: 504, message: '' } }
		if ( argRDRRes.ComStatus == 2 ) { return { code: 505, message: '' } }
		if ( argRDRRes.ICCStatus == 0 ) { return { code: 104, message: '' } }
		if ( argRDRRes.ICCStatus == 1 ) { return { code: 105, message: '' } }
		if ( argRDRRes.ICCStatus == 2 ) { return { code: 106, message: '' } }
		return this.ERRORFREE ;
	}

	/*
	*		エラーメッセージの取得
	----------------------------------------------------------------------*/
	getErrorMsg( argErno ) {
		let retVal = ( argErno in ArukasNFCLiteS.Errors ) ? ArukasNFCLiteS.Errors[ argErno ] : "Invalid Error Number. I couldn't find it." ;
		return retVal ;
	}

	/*
	*		エラーメッセージの表示
	----------------------------------------------------------------------*/
	putErrorMsg( argErr ) {
		if ( argErr === this.ERRORFREE ) return ;
		let eMsg =  this.getErrorMsg( argErr.code ) ;
		if ( argErr.code >= 500 ) {
			eMsg += ' ' + argErr.message + ' ' + this.mProcName ;
			let er = `Error(${ argErr.code }) [ ${ eMsg } ]` ;
			this.EcL( er ) ;
			throw ( { code: argErr.code, message: eMsg } ) ;
		} else {
			this.WcL( "(%d) [ %s %s ]", argErr.code, this.getErrorMsg( argErr.code ), argErr.message ) ;
		}
	}

	putErrorMsgToArray( argRes ) {
		for( let res of argRes ) {
			let err = res.Error
			this.putErrorMsg( err ) ;
		}
	}


	//	TransferIn Result Dataview -> array 変換
	dataview_to_array( argData ) {
		let retVal = new Array( argData.byteLength ) ;
		for( let i = 0 ; i < argData.byteLength ; ++i ) {
			retVal[i] = argData.getUint8(i) ;
		}
		return retVal ;
	}
	
	binToString( argData ) {
		for (let i = 0; i < argData.length; i++) {
			if ( argData[i] == 0x00 ) {
				argData[i] = 0x20 ;
			}
		}
		let text_decoder = new TextDecoder( "utf-8" );
		let retVal = text_decoder.decode( Uint8Array.from( argData ).buffer );
//		retVal = retVal.trim(' ') ;
		return retVal ;
	}

	// 初期値の設定
	def_val( param, def ) {
		return param || def ;
//		return (param === undefined) ? def : param;
	}

	array_slice( array, offset, length ) {
		let result;

		length = this.def_val(length, array.length - offset);
		result = [];
		this.array_copy(result, 0, array, offset, length);
		
		return result;
	}

	bytes2hexs( bytes, sep ) {
		sep = this.def_val(sep, ' ');

		return bytes.map( function( byte ) {
			let str = byte.toString(16) ;
			return byte < 0x10 ? '0' + str : str ;
		}).join( sep ).toUpperCase();
	}

	array_tohexs( array, sep ) {
		sep = this.def_val(sep, ' ');

		let temp = this.array_slice( array, 0, array.length );
		return this.bytes2hexs( temp, sep ) ;
	}

	array_tohexs_offset( array, offset, length, sep ) {
		offset = this.def_val( offset, 0 ) ;
		length = this.def_val( array.length, array.length - offset ) ;
		sep = this.def_val(sep, ' ');

		let temp = this.array_slice( array, offset, length );
		return this.bytes2hexs( temp, sep ) ;
	}

	array_copy( dest, dest_offset, src, src_offset, length ) {
		let idx ;

		src_offset = this.def_val( src_offset, 0 ) ;
		length = this.def_val( length, src.length ) ;

		for (idx = 0; idx < length; idx++) {
			dest[ dest_offset + idx ] = src[ src_offset + idx ];
		}
		return dest;
	}

	async sleep(msec) {
		return new Promise(resolve => setTimeout(resolve, msec));
	}

}

export { ArukasNFCLiteS } ;
